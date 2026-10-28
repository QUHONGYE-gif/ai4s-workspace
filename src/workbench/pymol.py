"""Control the existing personal PyMOL session from the workbench."""

from http.client import HTTPConnection
from pathlib import Path
from threading import RLock
from uuid import uuid4
from xmlrpc.client import ServerProxy, Transport


class LocalTransport(Transport):
    def make_connection(self, host):
        return HTTPConnection(host, timeout=15)


class PyMOLSession:
    object_name = "browser_structure"
    styles = {"cartoon", "sticks", "lines", "surface"}

    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = RLock()
        self.filename = None

    def connect(self):
        return ServerProxy(
            "http://127.0.0.1:9123", transport=LocalTransport(), allow_none=True
        )

    def status(self):
        with self.lock, self.connect() as pymol:
            pymol.ping()
            objects = pymol.getNames("objects")
            atoms = pymol.countAtoms(self.object_name) if self.object_name in objects else 0
            return {
                "ready": True,
                "filename": self.filename or "当前 PyMOL 结构",
                "atoms": atoms,
                **pymol.webGetMode(),
            }

    def load(self, filename, content, style):
        if not isinstance(filename, str) or Path(filename).suffix.lower() not in {
            ".pdb", ".cif", ".mmcif"
        }:
            raise ValueError("请选择 PDB 或 mmCIF 文件")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("结构文件为空")
        if len(content.encode("utf-8")) > 1024 * 1024:
            raise ValueError("请选择不超过 1 MiB 的结构文件")
        if not isinstance(style, str) or style not in self.styles:
            raise ValueError("不支持的显示方式")

        with self.lock, self.connect() as pymol:
            pymol.ping()
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / (uuid4().hex + Path(filename).suffix.lower())
            path.write_text(content, encoding="utf-8")
            self.filename = None
            pymol.loadFile(str(path), self.object_name)
            atoms = pymol.countAtoms(self.object_name)
            if not atoms:
                raise ValueError("PyMOL 未从此文件读取到原子，请检查文件内容")
            self.filename = Path(filename).name
            pymol.hide("everything", self.object_name)
            pymol.show(style, self.object_name)
            pymol.orient(self.object_name)
            return {"ready": True, "filename": self.filename, "atoms": atoms}

    def set_style(self, style):
        if not isinstance(style, str) or style not in self.styles:
            raise ValueError("不支持的显示方式")
        with self.lock, self.connect() as pymol:
            if self.object_name not in pymol.getNames("objects"):
                raise ValueError("请先加载一个结构文件")
            pymol.hide("everything", self.object_name)
            pymol.show(style, self.object_name)
            return {"style": style}

    def set_mode(self, full_ui):
        if not isinstance(full_ui, bool):
            raise ValueError("界面模式必须为布尔值")
        with self.lock, self.connect() as pymol:
            return pymol.webSetMode(full_ui)

    def execute(self, command):
        if not isinstance(command, str) or not command.strip():
            raise ValueError("请输入 PyMOL 命令")
        if len(command) > 4096:
            raise ValueError("单次命令不能超过 4096 个字符")
        with self.lock, self.connect() as pymol:
            return pymol.webExecute(command.strip())
