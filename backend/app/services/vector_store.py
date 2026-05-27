"""轻量化向量存储 — FAISS + NumPy本地持久化"""

from __future__ import annotations
import logging
import pickle
from pathlib import Path
import numpy as np

from app.utils.config import get_data_dir

logger = logging.getLogger(__name__)


class VectorStore:
    """轻量化向量存储，基于FAISS FlatIndex + 本地文件持久化"""

    def __init__(self, index_name: str = "default", dimension: int = 1024):
        self.index_name = index_name
        self.dimension = dimension
        # 使用不含中文的路径，FAISS 的 C 层 fopen 无法处理 Windows 上的 UTF-8 路径
        self.data_dir = Path.home() / ".geo-optimizer" / "vectors"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._index = None
        self._texts: list[str] = []
        self._metadata: list[dict] = []
        self._faiss_available = False

        try:
            import faiss
            self._faiss_available = True
        except ImportError:
            logger.warning("faiss-cpu未安装，降级使用NumPy线性搜索")

    @property
    def size(self) -> int:
        return len(self._texts)

    def add(self, texts: list[str], vectors: np.ndarray, metadata: list[dict] | None = None):
        """添加文本和向量到索引"""
        if len(texts) != len(vectors):
            raise ValueError(f"texts数量({len(texts)})与vectors数量({len(vectors)})不匹配")

        vectors = vectors.astype(np.float32)

        if self._faiss_available:
            self._add_faiss(vectors)
        else:
            self._add_numpy(vectors)

        self._texts.extend(texts)
        if metadata:
            self._metadata.extend(metadata)
        else:
            self._metadata.extend([{}] * len(texts))

        logger.info(f"向量存储[{self.index_name}] 已添加 {len(texts)} 条记录 (总计: {self.size})")

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[dict]:
        """语义搜索，返回top_k结果"""
        if self.size == 0:
            return []

        query_vector = query_vector.astype(np.float32).reshape(1, -1)

        if self._faiss_available and self._index is not None:
            scores, indices = self._index.search(query_vector, min(top_k, self.size))
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < self.size:
                    results.append({
                        "text": self._texts[idx],
                        "score": float(score),
                        "metadata": self._metadata[idx] if idx < len(self._metadata) else {},
                        "index": int(idx),
                    })
            return results
        else:
            return self._search_numpy(query_vector, top_k)

    def _add_faiss(self, vectors: np.ndarray):
        import faiss
        if self._index is None:
            self._index = faiss.IndexFlatIP(self.dimension)  # Inner Product = Cosine for normalized vectors
            # 如果已有旧数据，先加载
            self._load_index()
        self._index.add(vectors)

    def _add_numpy(self, vectors: np.ndarray):
        # 追加到numpy数组
        old_path = self.data_dir / f"{self.index_name}_vectors.npy"
        if old_path.exists() and self.size > 0:
            existing = self._load_numpy_vectors()
            vectors = np.vstack([existing, vectors])
        self._save_numpy_vectors(vectors)

    def _search_numpy(self, query_vector: np.ndarray, top_k: int) -> list[dict]:
        vectors = self._load_numpy_vectors()
        if vectors is None or len(vectors) == 0:
            return []
        scores = np.dot(vectors, query_vector.T).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if idx < len(self._texts):
                results.append({
                    "text": self._texts[idx],
                    "score": float(scores[idx]),
                    "metadata": self._metadata[idx] if idx < len(self._metadata) else {},
                    "index": int(idx),
                })
        return results

    def _save_numpy_vectors(self, vectors: np.ndarray):
        path = self.data_dir / f"{self.index_name}_vectors.npy"
        np.save(path, vectors)

    def _load_numpy_vectors(self) -> np.ndarray | None:
        path = self.data_dir / f"{self.index_name}_vectors.npy"
        if path.exists():
            return np.load(path)
        return None

    def save(self):
        """持久化保存索引、文本和元数据"""
        # 保存文本和元数据
        meta_path = self.data_dir / f"{self.index_name}_meta.pkl"
        with open(meta_path, "wb") as f:
            pickle.dump({"texts": self._texts, "metadata": self._metadata}, f)

        # FAISS索引 — 使用 serialize_index 通过 Python I/O 写入，避免 C 层 fopen 的 Windows 中文路径编码问题 [v2 fix]
        if self._faiss_available and self._index is not None:
            import faiss
            idx_path = self.data_dir / f"{self.index_name}_faiss.index"
            logger.info(f"使用 Python I/O 写入 FAISS 索引: {idx_path}")
            with open(idx_path, "wb") as f:
                f.write(faiss.serialize_index(self._index))
        else:
            # NumPy向量已在add时保存
            pass

        logger.info(f"向量存储[{self.index_name}] 已持久化 (记录数: {self.size})")

    def load(self) -> bool:
        """从文件加载索引"""
        meta_path = self.data_dir / f"{self.index_name}_meta.pkl"
        if not meta_path.exists():
            return False

        try:
            with open(meta_path, "rb") as f:
                data = pickle.load(f)
            self._texts = data.get("texts", [])
            self._metadata = data.get("metadata", [])
            self._load_index()
            logger.info(f"向量存储[{self.index_name}] 已加载 (记录数: {self.size})")
            return True
        except Exception as e:
            logger.warning(f"加载向量存储失败: {e}")
            return False

    def _load_index(self):
        """加载FAISS索引"""
        if not self._faiss_available:
            return
        idx_path = self.data_dir / f"{self.index_name}_faiss.index"
        if idx_path.exists():
            import faiss
            with open(idx_path, "rb") as f:
                self._index = faiss.deserialize_index(f.read())

    def clear(self):
        """清空存储"""
        self._index = None
        self._texts = []
        self._metadata = []
        for p in self.data_dir.glob(f"{self.index_name}_*"):
            p.unlink()
