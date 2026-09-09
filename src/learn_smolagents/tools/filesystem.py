from pathlib import Path

from smolagents import Tool, tool

from learn_smolagents.permissions import FileAccess


def build_file_tools(access: FileAccess) -> list[Tool]:
    """构建共享访问管理对象的工具，每次调用使用当前工作区。"""
    @tool
    def read_file(file_path: str) -> str:
        """
        读取指定 UTF-8 文件的完整文字内容。
        Args:
            file_path: 文件的路径。
        returns:
            文件内容的字符串表示。
        """
        path = access.check_permission(file_path, "读取文件")
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        if path.is_dir():
            raise IsADirectoryError(f"路径是目录，不能作为文件读取：{file_path}")
        if not path.is_file():
            raise ValueError(f"路径不是普通文件：{file_path}")
        return path.read_text(encoding="utf-8")


    @tool
    def list_directory(directory_path: str = ".") -> dict:
        """
        列出指定目录中的所有文件和子目录。
        Args:
            directory_path:要查看的目录路径，默认为当前目录。
        returns:
            目录内容的字符串表示，每个条目占一行。
        """
        path = access.check_permission(directory_path, "列出目录")
        if not path.exists():
            raise FileNotFoundError(f"错误: 目录 '{directory_path}' 不存在。")
        if not path.is_dir():
            raise NotADirectoryError(f"错误: '{directory_path}' 不是一个有效的目录。")

        dict_flie = []
        for item in path.iterdir():
            if item.is_file():
                dict_flie.append({"path": str(item.resolve()), "type": "file"})
            elif item.is_dir():
                dict_flie.append({"path": str(item.resolve()), "type": "directory"})
            elif item.is_symlink():
                dict_flie.append({"path": str(item.resolve()), "type": "symlink"})
            elif item.is_socket():
                dict_flie.append({"path": str(item.resolve()), "type": "socket"})
        return {"items": dict_flie}


    @tool
    def create_file(file_path: str, content: str = "") -> dict:
        """
        创建 UTF-8 文件并写入内容，拒绝覆盖已有文件。
        Args:
            file_path: 要创建的文件路径。
            content: 要写入文件的内容，默认为空字符串。
        returns:
            创建的文件路径的字符串表示以及写入的字节数。
        """
        path = access.check_permission(file_path, "创建文件")
        parent_dir = path.parent
        if not parent_dir.exists():
            raise FileNotFoundError(f"父目录不存在：{parent_dir}")
        if not parent_dir.is_dir():
            raise NotADirectoryError(f"父路径不是目录：{parent_dir}")

        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
        return {"path": str(path.resolve()), "bytes_written": len(content.encode("utf-8"))}


    @tool
    def edit_file(file_path: str, old_content: str, new_content: str) -> dict:
        """
        编辑 UTF-8 文件的内容，要求提供旧内容以验证一致性。
        Args:
            file_path: 要编辑的文件路径。
            old_content: 期望的旧内容，用于验证文件当前内容。
            new_content: 要写入的新内容。
        returns:
            编辑后的文件路径的字符串表示以及写入的字节数。
        """
        path = access.check_permission(file_path, "编辑文件")
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        if not path.is_file():
            raise ValueError(f"路径不是普通文件：{file_path}")
        if not old_content:
            raise ValueError("旧内容不能为空字符串，无法编辑。")

        with path.open("r", encoding="utf-8", newline="") as stream:
            string_content = stream.read()
            count = string_content.count(old_content)
            if count == 1:
                update = string_content.replace(old_content, new_content, 1)
            else:
                raise ValueError(
                    f"文件内容中未找到指定的旧内容或找到多次不够精确：{old_content},出现次数：{count}"
                )
        update = update.encode("utf-8")
        with path.open("wb") as stream:
            stream.write(update)

        return {"path": str(path.resolve()), "bytes_written": len(update)}


    @tool
    def search_file(search_string: str, directory_path: str = ".") -> dict:
        """
        递归搜索目录内的 UTF-8 文件，返回包含指定文字的行。
        Args:
            search_string: 要搜索的字符串。
            directory_path: 要搜索的目录路径，默认为当前目录。
        returns:
            搜索结果的字典表示，包括文件路径和匹配的行号列表以及文本内容。
        """
        path = access.check_permission(directory_path, "搜索目录")
        if not path.exists():
            raise FileNotFoundError(f"错误: 目录 '{directory_path}' 不存在。")
        if not path.is_dir():
            raise NotADirectoryError(f"错误: '{directory_path}' 不是一个有效的目录。")
        if not search_string:
            raise ValueError("搜索内容不能为空")

        results = []

        for item in path.rglob("*"):
            if not item.is_file():
                continue
            try:
                approved = access.check_permission(str(item), "搜索文件内容")
                content = approved.read_text(encoding="utf-8")
                for line_number, line in enumerate(content.splitlines(), start=1):
                    if search_string in line:
                        results.append(
                            {
                                "file_path": str(item.resolve()),
                                "line_number": line_number,
                                "text": line,
                            }
                        )
            except UnicodeDecodeError:
                continue
        return {"results": results}


    @tool
    def delete_file(file_path: str) -> dict:
        """删除单个普通文件，不接受目录或符号链接。

        Args:
            file_path: 要删除的普通文件路径。
        """
        original_path = Path(file_path)
        if not original_path.is_absolute():
            original_path = access.workspace.root / original_path
        if original_path.is_symlink():
            raise ValueError(f"不能使用此工具删除符号链接：{file_path}")
        path = access.check_permission(file_path, "删除文件")
        if path.is_symlink():
            raise ValueError(f"不能使用此工具删除符号链接：{file_path}")
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")
        if path.is_dir():
            raise IsADirectoryError(f"路径是目录：{file_path}")
        if not path.is_file():
            raise ValueError(f"路径不是普通文件：{file_path}")
        resolved = str(path.resolve())
        path.unlink()
        return {"path": resolved, "deleted": True}


    @tool
    def delete_directory(directory_path: str) -> dict:
        """删除单个空目录，非空目录会报错，不递归删除内容。

        Args:
            directory_path: 要删除的空目录路径，不接受符号链接。
        """
        original_path = Path(directory_path)
        if not original_path.is_absolute():
            original_path = access.workspace.root / original_path
        if original_path.is_symlink():
            raise ValueError(f"不能使用此工具删除符号链接：{directory_path}")
        path = access.check_permission(directory_path, "删除空目录")
        if path.is_symlink():
            raise ValueError(f"不能使用此工具删除符号链接：{directory_path}")
        if not path.exists():
            raise FileNotFoundError(f"目录不存在：{directory_path}")
        if not path.is_dir():
            raise NotADirectoryError(f"路径不是目录：{directory_path}")
        if any(path.iterdir()):
            raise ValueError(f"目录非空，不能删除：{directory_path}")
        resolved = str(path.resolve())
        path.rmdir()
        return {"path": resolved, "deleted": True}

    return [read_file, list_directory, create_file, edit_file, search_file, delete_file, delete_directory]
