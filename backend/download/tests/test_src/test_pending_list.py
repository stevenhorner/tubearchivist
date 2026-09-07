"""tests for PendingList functions"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from download.src.queue import PendingList


def test_returns_scientific_timestamp_if_present():
    video_data = {"timestamp": 1.5135732e9}
    result = PendingList._extract_published(video_data)
    assert result == 1513573200


def test_returns_scientific_timestamp_string_if_present():
    video_data = {"timestamp": "1.5135732e9"}
    result = PendingList._extract_published(video_data)
    assert result == 1513573200


def test_returns_timestamp_if_present():
    video_data = {"timestamp": 1508457600}
    result = PendingList._extract_published(video_data)
    assert result == 1508457600


def test_returns_iso_date_if_upload_date_present():
    video_data = {"upload_date": "20171020"}
    result = PendingList._extract_published(video_data)

    dt = datetime.fromtimestamp(result, tz=timezone.utc)
    assert dt.year == 2017
    assert dt.month == 10
    assert dt.day == 20
    assert dt.hour == 0
    assert dt.minute == 0
    assert dt.second == 0


def test_returns_None_if_no_date_info():
    video_data = {}

    result = PendingList._extract_published(video_data)

    assert result is None


def test_parse_url_list_snapshots_ta_video_before_ta_download(monkeypatch):
    call_order = []
    pending_list = PendingList.__new__(PendingList)
    pending_list.__dict__.update(youtube_ids=[], task=None, added=0)

    def snapshot(name):
        call_order.append(name)
        if name == "get_indexed":
            pending_list.to_skip = ["indexed"]
        elif name == "get_download":
            pending_list.to_skip = ["download"]

    for method in ("get_download", "get_indexed", "get_channels"):
        monkeypatch.setattr(
            pending_list, method, lambda name=method: snapshot(name)
        )

    pending_list.parse_url_list()

    assert call_order == ["get_indexed", "get_download", "get_channels"]
    assert pending_list.to_skip == ["download", "indexed"]


def test_add_to_pending_refreshes_bulk_write_when_ignoring(monkeypatch):
    pending_list = PendingList.__new__(PendingList)
    pending_list.__dict__.update(task=None, auto_start=False, force=True)
    pending_list.missing_videos = [
        {"youtube_id": "v", "channel_id": "c", "title": "t"}
    ]

    mock_wrap_cls = MagicMock()
    mock_wrap_cls.return_value.post.return_value = ({"errors": False}, 200)
    monkeypatch.setattr("download.src.queue.ElasticWrap", mock_wrap_cls)

    pending_list.add_to_pending(status="ignore")

    mock_wrap_cls.assert_called_once_with("_bulk?refresh=true")


def test_force_does_not_overwrite_existing_queue_items(monkeypatch):
    pending_list = PendingList.__new__(PendingList)
    pending_list.__dict__.update(
        force=True, auto_start=False, missing_videos=[]
    )
    parse_video = MagicMock()
    monkeypatch.setattr(pending_list, "_parse_video", parse_video)

    for status in ("all_ignored", "all_pending"):
        pending_list.all_ignored = []
        pending_list.all_pending = []
        setattr(pending_list, status, [{"youtube_id": "v"}])
        assert pending_list._add_video("v", "videos") is None

    parse_video.assert_not_called()
