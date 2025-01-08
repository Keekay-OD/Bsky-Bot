import logging
import mimetypes
import textwrap
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from time import time
from typing import Optional, Union

import httpx
from atproto import Client, models  # type: ignore
from atproto_client.exceptions import RequestException  # type: ignore
from mastodon import Mastodon as MastodonClient  # type: ignore

from .image import Image

try:
    POLYBOT_VERSION = version("polybot")
except PackageNotFoundError:
    POLYBOT_VERSION = "dev"


class PostError(Exception):
    """Raised when there was an error posting"""

    pass


class Service:
    name = None  # type: str
    ellipsis_length = 1
    max_length = None  # type: int
    max_length_image = None  # type: int
    max_image_size: int = int(10e6)
    max_image_pixels: Optional[int] = None
    max_image_count: int = 4

    def __init__(self, config, live: bool) -> None:
        self.log = logging.getLogger(__name__)
        self.config = config
        self.live = live
        self.user_agent = (
            f"Polybot/{POLYBOT_VERSION} (https://github.com/russss/polybot)"
        )

    def auth(self) -> None:
        raise NotImplementedError()

    def setup(self) -> bool:
        raise NotImplementedError()

    def longest_allowed(self, status: list, images: list[Image]) -> str:
        max_len = self.max_length_image if images else self.max_length
        picked = status[0]
        for s in sorted(status, key=len):
            if len(s) < max_len:
                picked = s
        return picked

    def post(
        self,
        status: Union[str, list[str]],
        wrap=False,
        images: list[Image] = [],
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        in_reply_to_id=None,
    ):
        images = [
            i.resize_to_target(self.max_image_size, self.max_image_pixels)
            for i in images[: self.max_image_count]
        ]
        if self.live:
            if wrap:
                return self.do_wrapped(status, images, lat, lon, in_reply_to_id)
            if isinstance(status, list):
                status = self.longest_allowed(status, images)
            return self.do_post(status, images, lat, lon, in_reply_to_id)

    def do_post(
        self,
        status: str,
        images: list[Image] = [],
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        in_reply_to_id=None,
    ):
        raise NotImplementedError()

    def do_wrapped(
        self,
        status,
        images: list[Image] = [],
        lat=None,
        lon=None,
        in_reply_to_id=None,
    ):
        max_len = self.max_length_image if images else self.max_length
        if len(status) > max_len:
            wrapped = textwrap.wrap(status, max_len - self.ellipsis_length)
        else:
            wrapped = [status]
        first = True
        for line in wrapped:
            if first and len(wrapped) > 1:
                line = line + "\u2026"
            if not first:
                line = "\u2026" + line

            if images and first:
                out = self.do_post(line, images, lat, lon, in_reply_to_id)
            else:
                out = self.do_post(
                    line, lat=lat, lon=lon, in_reply_to_id=in_reply_to_id
                )

            if isinstance(out, models.com.atproto.repo.strong_ref.Main):
                if first:
                    in_reply_to_id = {"root": out, "parent": out}
                else:
                    in_reply_to_id["parent"] = out
            elif hasattr(out, "id"):
                in_reply_to_id = out.id
            else:
                in_reply_to_id = out.data["id"]
            first = False



class Bluesky(Service):
    name = "bluesky"
    max_length = 300
    max_length_image = 300
    # As of 2024-12-03 the maximum image size allowed on Bluesky is 1 metric megabyte.
    max_image_size = int(1e6)

    def __init__(self, config, live: bool):
        super().__init__(config, live)
        self.login_ratelimit_expiry = 0
        self.connected = False

    def auth(self):
        self.bluesky = Client()
        if self.login_ratelimit_expiry > time():
            self.log.warning(
                "Not connecting to Bluesky as login rate limit is still active. "
                "Will re-attempt connection in %d seconds.",
                self.login_ratelimit_expiry - time(),
            )
            return

        try:
            self.bluesky.login(
                self.config.get("bluesky", "email"),
                self.config.get("bluesky", "password"),
            )
        except RequestException as e:
            if e.response.status_code == 429:
                self.login_ratelimit_expiry = int(e.response.headers["ratelimit-reset"])
                self.log.warning(
                    "Rate-limited by Bluesky when connecting. "
                    "Will re-attempt connection in %d seconds.",
                    self.login_ratelimit_expiry - time(),
                )
                return
            raise

        self.connected = True
        self.log.info("Connected to Bluesky")

    def setup(self):
        print("We need your Bluesky email and password")
        email = input("Email: ")
        password = input("Password: ")
        self.config.add_section("bluesky")
        self.config.set("bluesky", "email", email)
        self.config.set("bluesky", "password", password)
        return True

    def do_post(
        self,
        status,
        images: list[Image] = [],
        lat=None,
        lon=None,
        in_reply_to_id=None,
    ):
        if not self.connected:
            self.auth()

        if not self.connected:
            self.log.warning("Skipping Bluesky post, not connected")
            return

        if in_reply_to_id:
            in_reply_to_id = models.AppBskyFeedPost.ReplyRef(
                parent=in_reply_to_id["parent"], root=in_reply_to_id["root"]
            )
        try:
            if len(images) > 0:
                resp = self.bluesky.send_images(
                    status,
                    [i.data for i in images],
                    [i.description for i in images],
                    self.bluesky.me.did,
                    in_reply_to_id,
                )
            else:
                resp = self.bluesky.send_post(
                    status, self.bluesky.me.did, in_reply_to_id
                )
            return models.create_strong_ref(resp)

        except Exception as e:
            raise PostError(e)


ALL_SERVICES: list[type[Service]] = [Bluesky]
