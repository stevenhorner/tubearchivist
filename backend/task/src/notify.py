"""send notifications using apprise"""

import apprise
from apprise import NotifyFormat
from common.src.env_settings import EnvironmentSettings
from common.src.es_connect import ElasticWrap
from task.src.task_config import TASK_CONFIG
from task.src.task_manager import TaskManager


class Notifications:
    """store notifications in ES"""

    GET_PATH = "ta_config/_doc/notify"
    UPDATE_PATH = "ta_config/_update/notify/"

    def __init__(self, task_name: str):
        self.task_name = task_name

    def send(self, task_id: str, task_title: str) -> None:
        """send notifications"""
        apobj = apprise.Apprise()
        urls: list[str] = self.get_urls()
        if not urls:
            return

        title, body, attach_urls = self._build_message(task_id, task_title)

        if not body:
            return

        for url in urls:
            apobj.add(url)

        apobj.notify(
            body=body,
            title=title,
            body_format=NotifyFormat.MARKDOWN,
            attach=attach_urls if attach_urls else None,
        )

    def test(self, url) -> tuple[bool, str]:
        """send test notification"""
        try:
            apobj = apprise.Apprise()

            if not apobj.add(url):
                success = False
                message = f"Invalid notification URL format: {url}"
                return success, message

            title = f"[TA] {self.task_name} process ended with SUCCESS"
            body = "This is a test notification. Task completed successfully."

            result = apobj.notify(body=body, title=title)

            if result:
                success = True
                message = "Test notification sent successfully"
                return success, message

            success = False
            message = (
                "Notification failed. "
                "Please check container logs for more information."
            )
            return success, message

        except Exception as err:  # pylint: disable=broad-exception-caught
            success = False
            message = f"Notification error: {str(err)}"
            return success, message

    def _build_message(
        self, task_id: str, task_title: str
    ) -> tuple[str, str | None, list[str] | None]:
        """build message to send notification"""
        task = TaskManager().get_task(task_id)
        status = task.get("status")
        title: str = f"[TA] {task_title} process ended with {status}"
        result = task.get("result")

        if isinstance(result, dict) and "videos" in result:
            body, attach_urls = self._format_video_details(result)
        else:
            body: str | None = result if isinstance(result, str) else None
            attach_urls = None

        return title, body, attach_urls

    def _format_video_details(
        self, result: dict
    ) -> tuple[str, list[str] | None]:
        """format video details for notification using markdown"""
        from datetime import datetime

        message_lines = [result.get("message", "")]
        videos = result.get("videos", [])

        if not videos:
            return message_lines[0], None

        message_lines.append("\n## 📹 Downloaded Videos\n")
        attach_urls = []

        for idx, video in enumerate(videos, 1):
            title = video.get("title", "Unknown Title")
            channel_name = video.get("channel_name", "Unknown Channel")
            youtube_id = video.get("youtube_id", "")
            duration = video.get("duration", "")
            published = video.get("published", "")
            thumb_url = video.get("vid_thumb_url", "")

            if thumb_url and len(attach_urls) < 3:
                attach_urls.append(thumb_url)

            video_url = f"https://www.youtube.com/watch?v={youtube_id}"
            ta_host = EnvironmentSettings.TA_HOST.split()[0]
            ta_video_url = f"{ta_host}/video/{youtube_id}"

            message_lines.append(f"### {idx}. {title}\n")
            if thumb_url:
                message_lines.append(f"![Thumbnail]({thumb_url})\n")

            message_lines.append(f"**Channel:** {channel_name}  ")
            if duration:
                message_lines.append(f"**Duration:** {duration}  ")

            if published:
                try:
                    pub_date = datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    )
                    published = pub_date.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    pass
                message_lines.append(f"**Published:** {published}  ")

            message_lines.append(
                f"**Watch:** [TubeArchivist]({ta_video_url}) | "
                f"[YouTube]({video_url})\n"
            )
            message_lines.append("")

        body = "\n".join(message_lines)
        return body, attach_urls if attach_urls else None

    def get_urls(self) -> list[str]:
        """get stored urls for task"""
        response, code = ElasticWrap(self.GET_PATH).get(print_error=False)
        if not code == 200:
            return []

        urls = response["_source"].get(self.task_name, [])

        return urls

    def add_url(self, url: str) -> None:
        """add url to task notification"""
        source = (
            "if (!ctx._source.containsKey(params.task_name)) "
            + "{ctx._source[params.task_name] = [params.url]} "
            + "else if (!ctx._source[params.task_name].contains(params.url)) "
            + "{ctx._source[params.task_name].add(params.url)} "
            + "else {ctx.op = 'none'}"
        )

        data = {
            "script": {
                "source": source,
                "lang": "painless",
                "params": {"url": url, "task_name": self.task_name},
            },
            "upsert": {self.task_name: [url]},
        }

        _, _ = ElasticWrap(self.UPDATE_PATH).post(data)

    def remove_url(self, url: str) -> tuple[dict, int]:
        """remove url from task"""
        source = (
            "if (ctx._source.containsKey(params.task_name) "
            + "&& ctx._source[params.task_name].contains(params.url)) "
            + "{ctx._source[params.task_name]."
            + "remove(ctx._source[params.task_name].indexOf(params.url))}"
        )

        data = {
            "script": {
                "source": source,
                "lang": "painless",
                "params": {"url": url, "task_name": self.task_name},
            }
        }

        response, status_code = ElasticWrap(self.UPDATE_PATH).post(data)
        if not self.get_urls():
            _, _ = self.remove_task()

        return response, status_code

    def remove_task(self) -> tuple[dict, int]:
        """remove all notifications from task"""
        source = (
            "if (ctx._source.containsKey(params.task_name)) "
            + "{ctx._source.remove(params.task_name)}"
        )
        data = {
            "script": {
                "source": source,
                "lang": "painless",
                "params": {"task_name": self.task_name},
            }
        }

        response, status_code = ElasticWrap(self.UPDATE_PATH).post(data)

        return response, status_code


def get_all_notifications() -> dict[str, list[str]]:
    """get all notifications stored"""
    path = "ta_config/_doc/notify"
    response, status_code = ElasticWrap(path).get(print_error=False)
    if not status_code == 200:
        return {}

    notifications: dict = {}
    source = response.get("_source")
    if not source:
        return notifications

    for task_id, urls in source.items():
        notifications.update(
            {
                task_id: {
                    "urls": urls,
                    "title": TASK_CONFIG[task_id]["title"],
                }
            }
        )

    return notifications
