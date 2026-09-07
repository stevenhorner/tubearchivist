"""tests for DownloadPostProcess auto delete watched race"""

from unittest.mock import MagicMock, patch

from download.src.yt_dlp_handler import DownloadPostProcess


def test_auto_delete_watched_adds_ignore_before_removing_from_ta_video():
    """ignore-list write must precede removal from ta_video"""
    call_order = []
    video = {"youtube_id": "abc123", "vid_type": "videos"}

    youtube_video = MagicMock()
    youtube_video.return_value.delete_media_file.side_effect = (
        lambda: call_order.append("delete")
    )
    pending_list = MagicMock()
    pending_list.return_value.parse_url_list.side_effect = (
        lambda **_kwargs: call_order.append("ignore")
    )
    elastic = MagicMock()
    elastic.return_value.get.return_value = (
        {
            "docs": [
                {
                    "_id": "abc123",
                    "found": True,
                    "_source": {"status": "ignore"},
                }
            ]
        },
        200,
    )

    with patch("download.src.yt_dlp_handler.IndexPaginate") as paginate, patch(
        "download.src.yt_dlp_handler.YoutubeVideo", youtube_video
    ), patch("download.src.yt_dlp_handler.PendingList", pending_list), patch(
        "download.src.yt_dlp_handler.ElasticWrap", elastic
    ):
        paginate.return_value.get_results.return_value = [video]
        DownloadPostProcess._auto_delete_watched({"query": {"match_all": {}}})

    assert pending_list.call_args.kwargs["force"] is True
    assert call_order == ["ignore", "delete"]


def test_auto_delete_watched_keeps_video_when_ignore_is_missing():
    video = {"youtube_id": "abc123", "vid_type": "videos"}
    with patch("download.src.yt_dlp_handler.IndexPaginate") as paginate, patch(
        "download.src.yt_dlp_handler.YoutubeVideo"
    ) as youtube_video, patch(
        "download.src.yt_dlp_handler.PendingList"
    ), patch(
        "download.src.yt_dlp_handler.ElasticWrap"
    ) as elastic:
        paginate.return_value.get_results.return_value = [video]
        elastic.return_value.get.return_value = ({"docs": []}, 200)
        DownloadPostProcess._auto_delete_watched({})

    youtube_video.assert_not_called()
