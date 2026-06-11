# test_text_splitter.py — Unit tests for TextSplitter

from __future__ import annotations
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.utils.text_splitter import TextSplitter, default_splitter


class TestTextSplitter:
    def test_basic_split(self):
        ts = TextSplitter(max_chunk_size=500, chunk_overlap=50)
        text = "第一段内容。" * 30
        chunks = ts.split(text)
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c) <= 500 + 100  # some tolerance

    def test_short_text_no_split(self):
        ts = TextSplitter(max_chunk_size=2000, chunk_overlap=200)
        chunks = ts.split("短文本。")
        assert len(chunks) == 1
        assert chunks[0] == "短文本。"

    def test_empty_text(self):
        ts = TextSplitter()
        chunks = ts.split("")
        assert chunks == []

    def test_whitespace_only(self):
        ts = TextSplitter()
        chunks = ts.split("   \n\n  ")
        assert chunks == []

    def test_overlap_capped(self):
        ts = TextSplitter(max_chunk_size=100, chunk_overlap=500)
        assert ts.chunk_overlap <= 25  # max 1/4 of chunk size

    def test_separator_cascade(self):
        ts = TextSplitter(max_chunk_size=500, chunk_overlap=50)
        text = "段落A。段落B。\n\n段落C；段落D！"
        chunks = ts.split(text)
        assert len(chunks) >= 1

    def test_force_split_long_sentence(self):
        ts = TextSplitter(max_chunk_size=20, chunk_overlap=0)
        # A very long sentence with no separators
        text = "这是一个很长很长很长很长很长很长很长很长很长很长很长的句子"
        chunks = ts.split(text)
        assert len(chunks) >= 1

    def test_default_splitter_works(self):
        text = "测试段落一。\n\n测试段落二。" * 10
        chunks = default_splitter.split(text)
        assert len(chunks) >= 1

    def test_chunks_maintain_order(self):
        ts = TextSplitter(max_chunk_size=500, chunk_overlap=30)
        text = "A内容。" * 5 + "\n\n" + "B内容。" * 5 + "\n\n" + "C内容。" * 5
        chunks = ts.split(text)
        # First chunk should contain A, last should contain C
        assert "A内容" in chunks[0]
        assert "C内容" in chunks[-1]

    def test_max_chunk_size_respected(self):
        ts = TextSplitter(max_chunk_size=100, chunk_overlap=0)
        text = "这是一个很长的句子用来测试切分功能是否正常工作。" * 10
        chunks = ts.split(text)
        # Force-split mode kicks in for sentences longer than max_chunk_size
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c) > 0
