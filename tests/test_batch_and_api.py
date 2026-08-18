from ai_watermark_toolkit.batch import process_batch


def test_batch_pipeline(tmp_path):
    src = tmp_path / "in"
    dst = tmp_path / "out"
    src.mkdir()
    (src / "a.txt").write_text(
        "In today's digital world, it is important to note that tools leverage automation.", encoding="utf-8"
    )
    report = process_batch(str(src), str(dst), mode="pipeline", intensity="standard", lang="en")
    assert report["count"] == 1
    assert (dst / "a.txt").exists()
    assert (dst / "a.txt.report.json").exists()
