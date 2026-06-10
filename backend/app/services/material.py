import os
import random
import threading
from typing import List
from urllib.parse import urlencode

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip
from PIL import Image

from app.config import config
from app.models import const
from app.models.schema import MaterialInfo, MaterialType, VideoAspect, VideoConcatMode
from app.utils import utils

# Thread-safe counter for API key rotation
_api_key_counter = 0
_api_key_lock = threading.Lock()


def _get_tls_verify() -> bool:
    # 默认开启 TLS 证书校验，防止素材搜索和下载过程被中间人篡改。
    # 仅在企业代理、自签证书等明确需要的场景下，允许用户通过
    # `config.toml` 显式设置 `tls_verify = false` 临时关闭。
    tls_verify = config.app.get("tls_verify", True)
    if isinstance(tls_verify, str):
        tls_verify = tls_verify.strip().lower() not in ("0", "false", "no", "off")

    if not tls_verify:
        logger.warning(
            "TLS certificate verification is disabled by config.app.tls_verify=false. "
            "Only use this in trusted proxy environments."
        )

    return bool(tls_verify)


def get_api_key(cfg_key: str):
    from app.services.credentials import cfg

    api_keys = cfg(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global _api_key_counter
    with _api_key_lock:
        _api_key_counter += 1
        return api_keys[_api_key_counter % len(api_keys)]


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    # Build URL
    params = {"query": search_term, "per_page": 40, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url,
            headers=headers,
            proxies=config.proxy,
            verify=_get_tls_verify(),
            timeout=(30, 60),
        )
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["videos"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["video_files"]
            # loop through each url to determine the best quality
            for video in video_files:
                w = int(video["width"])
                h = int(video["height"])
                if w == video_width and h == video_height:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    video_width, video_height = aspect.to_resolution()

    api_key = get_api_key("pixabay_api_keys")
    # Build URL
    params = {
        "q": search_term,
        "video_type": "all",  # Accepted values: "all", "film", "animation"
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url, proxies=config.proxy, verify=_get_tls_verify(), timeout=(30, 60)
        )
        response = r.json()
        video_items = []
        if "hits" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["hits"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["videos"]
            # loop through each url to determine the best quality
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video["width"])
                # h = int(video["height"])
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def search_images_pexels(
    search_term: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    # Pexels photo API accepts orientation: landscape | portrait | square — matches aspect.name.
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    params = {"query": search_term, "per_page": 50, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/v1/search?{urlencode(params)}"
    logger.info(f"searching images: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url,
            headers=headers,
            proxies=config.proxy,
            verify=_get_tls_verify(),
            timeout=(30, 60),
        )
        response = r.json()
        image_items = []
        if "photos" not in response:
            logger.error(f"search images failed: {response}")
            return image_items
        for photo in response["photos"]:
            w = int(photo.get("width", 0))
            h = int(photo.get("height", 0))
            # Skip images that are too small to avoid blurry upscaling (480x480 floor, like preprocess_video).
            if w < 480 or h < 480:
                continue
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("original") or src.get("large")
            if not url:
                continue
            item = MaterialInfo()
            item.provider = "pexels"
            item.type = MaterialType.image.value
            item.url = url
            item.duration = 0
            image_items.append(item)
        return image_items
    except Exception as e:
        logger.error(f"search images failed: {str(e)}")

    return []


def search_images_pixabay(
    search_term: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()
    # Pixabay accepts orientation: all | horizontal | vertical.
    orientation_map = {
        VideoAspect.landscape.name: "horizontal",
        VideoAspect.portrait.name: "vertical",
        VideoAspect.square.name: "all",
    }
    api_key = get_api_key("pixabay_api_keys")
    params = {
        "q": search_term,
        "image_type": "photo",
        "per_page": 50,
        "key": api_key,
        "orientation": orientation_map.get(aspect.name, "all"),
        "min_width": video_width,
        "min_height": video_height,
    }
    query_url = f"https://pixabay.com/api/?{urlencode(params)}"
    logger.info(f"searching images: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url, proxies=config.proxy, verify=_get_tls_verify(), timeout=(30, 60)
        )
        response = r.json()
        image_items = []
        if "hits" not in response:
            logger.error(f"search images failed: {response}")
            return image_items
        for hit in response["hits"]:
            url = (
                hit.get("largeImageURL")
                or hit.get("fullHDURL")
                or hit.get("webformatURL")
            )
            if not url:
                continue
            item = MaterialInfo()
            item.provider = "pixabay"
            item.type = MaterialType.image.value
            item.url = url
            item.duration = 0
            image_items.append(item)
        return image_items
    except Exception as e:
        logger.error(f"search images failed: {str(e)}")

    return []


def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # if video does not exist, download it
    with open(video_path, "wb") as f:
        f.write(
            requests.get(
                video_url,
                headers=headers,
                proxies=config.proxy,
                verify=_get_tls_verify(),
                timeout=(60, 240),
            ).content
        )

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        clip = None
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            if duration > 0 and fps > 0:
                return video_path
        except Exception as e:
            logger.warning(f"invalid video file: {video_path} => {str(e)}")
            try:
                os.remove(video_path)
            except Exception as remove_error:
                logger.warning(
                    f"failed to remove invalid video file: {video_path}, error: {str(remove_error)}"
                )
        finally:
            if clip is not None:
                try:
                    clip.close()
                except Exception as close_error:
                    logger.warning(
                        f"failed to close video clip: {video_path}, error: {str(close_error)}"
                    )
    return ""


def save_image(image_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_images")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = image_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    ext = os.path.splitext(url_without_query)[1].lstrip(".").lower()
    if ext not in const.FILE_TYPE_IMAGES:
        ext = "jpg"
    image_path = f"{save_dir}/img-{url_hash}.{ext}"

    # if image already exists, return the path
    if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
        logger.info(f"image already exists: {image_path}")
        return image_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    with open(image_path, "wb") as f:
        f.write(
            requests.get(
                image_url,
                headers=headers,
                proxies=config.proxy,
                verify=_get_tls_verify(),
                timeout=(60, 240),
            ).content
        )

    if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
        try:
            # Validate with Pillow (already a dependency) to avoid coupling material.py to moviepy.
            with Image.open(image_path) as im:
                im.verify()
            return image_path
        except Exception as e:
            logger.warning(f"invalid image file: {image_path} => {str(e)}")
            try:
                os.remove(image_path)
            except Exception as remove_error:
                logger.warning(
                    f"failed to remove invalid image file: {image_path}, error: {str(remove_error)}"
                )
    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    search_videos = search_videos_pexels
    if source == "pixabay":
        search_videos = search_videos_pixabay

    for search_term in search_terms:
        video_items = search_videos(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        logger.info(f"found {len(video_items)} videos for '{search_term}'")

        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    concat_mode_value = getattr(video_contact_mode, "value", video_contact_mode)
    if concat_mode_value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(
                video_url=item.url, save_dir=material_directory
            )
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration of downloaded videos: {total_duration} seconds, skip downloading more"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
    logger.success(f"downloaded {len(video_paths)} videos")
    return video_paths


def download_materials(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    material_types: List[str] = ("video", "image"),
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
    image_clip_duration: int = 4,
    convert_images_to_clips: bool = True,
    min_count: int = 0,
    max_materials: int = 0,
) -> List[str]:
    """Search + download a mix of VIDEOS and IMAGES by keyword; return ready-to-use local paths.

    When convert_images_to_clips=True, images are turned into .mp4 clips (Ken-Burns zoom)
    so the caller sees a uniform list of .mp4 files.

    Stops once total duration covers audio_duration AND at least `min_count` unique clips
    are downloaded — beat-sync uses one clip per (short) segment, so it needs a clip *count*,
    not just total duration, to avoid repeating the same clips. Never exceeds `max_materials`
    (0 = no extra cap) to bound API cost / bandwidth.
    """
    material_types = [t for t in material_types] or ["video"]
    search_video = search_videos_pixabay if source == "pixabay" else search_videos_pexels
    search_image = search_images_pixabay if source == "pixabay" else search_images_pexels

    valid_items = []
    valid_urls = set()
    found_duration = 0.0

    for search_term in search_terms:
        items = []
        if "video" in material_types:
            items += search_video(
                search_term=search_term,
                minimum_duration=max_clip_duration,
                video_aspect=video_aspect,
            )
        if "image" in material_types:
            items += search_image(
                search_term=search_term,
                video_aspect=video_aspect,
            )
        logger.info(f"found {len(items)} materials for '{search_term}'")
        for item in items:
            if item.url not in valid_urls:
                valid_items.append(item)
                valid_urls.add(item.url)
                found_duration += item.duration if item.type == MaterialType.video.value else image_clip_duration

    logger.info(
        f"found total materials: {len(valid_items)}, required duration: {audio_duration}s, found duration: {found_duration}s"
    )

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    concat_mode_value = getattr(video_contact_mode, "value", video_contact_mode)
    if concat_mode_value in (VideoConcatMode.random.value, VideoConcatMode.beat_sync.value):
        random.shuffle(valid_items)

    material_paths = []
    total_duration = 0.0
    for item in valid_items:
        try:
            if item.type == MaterialType.image.value:
                logger.info(f"downloading image: {item.url}")
                saved_path = save_image(image_url=item.url, save_dir=material_directory)
                if saved_path and convert_images_to_clips:
                    # Lazy import to avoid a circular import (video.py does not import material.py).
                    from app.services.video import image_to_clip_file

                    saved_path = image_to_clip_file(
                        image_path=saved_path,
                        clip_duration=image_clip_duration,
                        video_aspect=video_aspect,
                    )
                seconds = image_clip_duration
            else:
                logger.info(f"downloading video: {item.url}")
                saved_path = save_video(video_url=item.url, save_dir=material_directory)
                seconds = min(max_clip_duration, item.duration)

            if saved_path:
                logger.info(f"material saved: {saved_path}")
                material_paths.append(saved_path)
                total_duration += seconds
                if max_materials and len(material_paths) >= max_materials:
                    logger.info(
                        f"reached max_materials={max_materials}, stop downloading "
                        f"(some clips may repeat for very long videos)"
                    )
                    break
                # Need both enough duration AND enough distinct clips (for beat-sync segments).
                if total_duration > audio_duration and len(material_paths) >= min_count:
                    logger.info(
                        f"downloaded {len(material_paths)} clips covering {total_duration}s, "
                        f"skip downloading more"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download material: {utils.to_json(item)} => {str(e)}")

    logger.success(f"downloaded {len(material_paths)} materials")
    return material_paths


if __name__ == "__main__":
    download_videos(
        "test123", ["Money Exchange Medium"], audio_duration=100, source="pixabay"
    )
