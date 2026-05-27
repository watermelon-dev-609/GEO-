"""自适应文本切片 — 语义段落切分 + 滑动窗口"""

import re
from typing import Iterator


class TextSplitter:
    """智能文本切片器"""

    def __init__(
        self,
        max_chunk_size: int = 2000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = min(chunk_overlap, max_chunk_size // 4)
        self.separators = separators or ["\n\n", "\n", "。", "；", "！", "？", ". ", "; ", "! ", "? "]

    def split(self, text: str) -> list[str]:
        """将文本切分为多个有重叠的语义块"""
        paragraphs = self._split_by_separators(text)
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current) + len(para) <= self.max_chunk_size:
                current += para
            else:
                if current:
                    chunks.append(current.strip())
                # 如果当前段落太长，递归切分
                if len(para) > self.max_chunk_size:
                    sub_chunks = self._force_split(para)
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    # 重叠：从上一块的末尾取重叠部分
                    overlap_text = current[-self.chunk_overlap:] if current and len(chunks) > 0 else ""
                    current = overlap_text + para

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def split_flat(self, text: str) -> list[str]:
        """无重叠切分（用于向量检索）"""
        return [
            text[i:i + self.max_chunk_size]
            for i in range(0, len(text), self.max_chunk_size - self.chunk_overlap)
        ]

    def _split_by_separators(self, text: str) -> list[str]:
        """按分隔符逐级拆分"""
        for sep in self.separators:
            if sep in text:
                return self._recombine_short(text.split(sep), sep)
        return [text]

    def _recombine_short(self, parts: list[str], sep: str) -> list[str]:
        """合并过短的片段"""
        result = []
        buffer = ""
        min_len = self.max_chunk_size // 4
        for part in parts:
            if buffer and len(buffer) + len(part) + len(sep) < min_len:
                buffer += sep + part
            else:
                if buffer:
                    result.append(buffer)
                buffer = part
        if buffer:
            result.append(buffer)
        return result

    def _force_split(self, text: str) -> list[str]:
        """强制按长度切分长文本"""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chunk_size, len(text))
            # 尝试在句子边界处切分
            if end < len(text):
                for sep in ["。", "；", "！", "？", ". ", "; "]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + self.max_chunk_size // 2:
                        end = last_sep + len(sep)
                        break
            chunks.append(text[start:end].strip())
            start = end - self.chunk_overlap if end < len(text) else end
        return chunks

    def stream_split(self, text: str) -> Iterator[str]:
        """流式切分（用于大文本渐进处理）"""
        for chunk in self.split(text):
            yield chunk


# 默认实例
default_splitter = TextSplitter()
