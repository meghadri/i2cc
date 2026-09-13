import base64
import gzip
import json
import marshal
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from types import CodeType
from typing import Any, Self

import requests
from rgscore import RegList

PROJECT_RE = re.compile("^[a-zA-Z0-9_]+$")
PROJECT_VALID_CHAR_RE = re.compile("[a-zA-Z0-9_]")


class CommandsContext:
    def __init__(self):
        self.__context_attributes = dict()

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "_CommandsContext__context_attributes":
            super().__setattr__(key, value)
        else:
            self.__context_attributes[key] = value

    def __getattribute__(self, name: str, /) -> Any:
        if name == "_CommandsContext__context_attributes":
            return super().__getattribute__(name)
        else:
            try:
                return self.__context_attributes[name]
            except KeyError:
                return None


@dataclass
class CustomCommand:
    label: str
    source_code: str
    compiled_code: CodeType
    compiled_code_txt: str | None = None

    def __post_init__(self):
        if self.compiled_code_txt is None:
            self.compiled_code_txt = base64.encodebytes(marshal.dumps(self.compiled_code)).decode("utf-8")

    def to_dict(self) -> dict[str, str]:
        assert self.compiled_code_txt is not None
        return {
            "label": self.label,
            "source_code": self.source_code,
            "compiled_code": self.compiled_code_txt,
        }

    @staticmethod
    def from_dict(data: dict[str, str]) -> "CustomCommand":
        return CustomCommand(
            label=data["label"],
            source_code=data["source_code"],
            compiled_code=marshal.loads(base64.decodebytes(data["compiled_code"].encode("utf-8"))),
            compiled_code_txt=data["compiled_code"],
        )


@dataclass
class RawResult:
    name_and_address: str
    value_hex: str
    value_bin: str
    address: int
    address_bus_width_in_bytes: int

    def get_value_at_column(self, column: int) -> str:
        match column:
            case 0:
                return self.name_and_address
            case 1:
                return self.value_hex
            case 2:
                return self.value_bin
            case _:
                return ""

    @staticmethod
    def from_dict_def(data: dict) -> "RawResult":
        return RawResult(
            name_and_address=data["name_and_address"],
            value_hex=data["value_hex"],
            value_bin=data["value_bin"],
            address=data["address"],
            address_bus_width_in_bytes=data["address_bus_width_in_bytes"],
        )


class Project:
    version: int = 1

    def __init__(self, name: str, dir: Path):
        self.name = name
        self.dir = dir
        self.commands_context = CommandsContext()

        if not self.commands_path.exists():
            self.commands_path.write_text("[]")

        self.reg_list = RegList()
        if not self.reg_list_path.exists():
            self.save_reglist()

        self.notes = ""
        if not self.notes_markdown_path.exists():
            self.save_notes()

        self.results: list[RawResult] = []
        self.commands: list[CustomCommand] = []
        self.commands_by_label: dict[str, CustomCommand] = dict()

    @property
    def notes_markdown_path(self) -> Path:
        return self.dir / "notes.md"

    @property
    def version_json_path(self) -> Path:
        return self.dir / "version.json"

    @property
    def reg_list_path(self) -> Path:
        return self.dir / "regList.json"

    @property
    def results_path(self) -> Path:
        return self.dir / "results.json"

    @property
    def commands_path(self) -> Path:
        return self.dir / "commands.json"

    def rename(self, name: str) -> str:
        """
        Rename this project with new name. If rename succeeds, then return old/original project name, otherwise
        error is raised.
        """
        if not PROJECT_RE.match(name):
            raise ValueError("Project name must consist of only letters, numbers and underscore characters.")
        old_name = self.name
        self.name = name
        new_dir = (self.dir.parent / name).absolute()
        self.dir = self.dir.rename(new_dir)
        return old_name

    def export_to_file(self, file_out: Path | str, override_if_exists: bool):
        file_out_path = Path(file_out)
        if file_out_path.exists() and not override_if_exists:
            raise ValueError(f"File {file_out_path.absolute()} already exists")

        data_to_export = {
            "project_name": self.name,
            "version": json.loads(self.version_json_path.read_text()),
            "regList": json.loads(self.reg_list_path.read_text()),
            "commands": json.loads(self.commands_path.read_text()),
            "notes": self.notes_markdown_path.read_text(),
        }
        with gzip.open(file_out_path, "wb") as f:
            f.write(json.dumps(data_to_export).encode())

    def get_raw_result_for_address(self, register_address: int) -> RawResult | None:
        for row in self.results:
            if row.address == register_address:
                return row
        return None

    def add_custom_command(self, command: CustomCommand):
        self.commands.append(command)
        self.commands.sort(key=lambda cmd: cmd.label.lower())
        self.commands_by_label[command.label] = command
        self.save_commands()

    def update_custom_command(self, original_cmd: CustomCommand, new_cmd: CustomCommand):
        self.delete_custom_command(original_cmd.label, auto_save=False)
        self.add_custom_command(new_cmd)

    def get_custom_command_by_label(self, label: str) -> CustomCommand | None:
        return self.commands_by_label.get(label, None)

    def delete_custom_command(self, label: str, auto_save: bool = True):
        match self.get_custom_command_by_label(label):
            case CustomCommand() as cmd:
                try:
                    idx = self.commands.index(cmd)
                    del self.commands[idx]
                    del self.commands_by_label[label]
                    if auto_save:
                        self.save_commands()
                except ValueError:
                    pass

    def copy_to(self, target_project: "Project"):
        target_project.version_json_path.write_bytes(self.version_json_path.read_bytes())
        target_project.reg_list_path.write_bytes(self.reg_list_path.read_bytes())
        target_project.results_path.write_bytes(self.results_path.read_bytes())
        target_project.commands_path.write_bytes(self.commands_path.read_bytes())
        target_project.notes_markdown_path.write_bytes(self.notes_markdown_path.read_bytes())

    def load(self) -> Self:
        version = json.loads(self.version_json_path.read_text())["version"]
        if version != 1:
            raise RuntimeError(f"Unable to load project version {version}")
        self.reg_list = RegList.from_json_def(self.reg_list_path.read_text())
        self.notes = self.notes_markdown_path.read_text()

        self.results = [RawResult(**row) for row in json.loads(self.results_path.read_text())]
        self.commands.clear()
        self.commands.extend([CustomCommand.from_dict(row) for row in json.loads(self.commands_path.read_text())])
        self.commands_by_label.clear()
        for cmd in self.commands:
            self.commands_by_label[cmd.label] = cmd

        return self

    def save(self) -> Self:
        if self.dir.exists():
            self.version_json_path.write_text(json.dumps({"version": Project.version}))
            self.save_results()
            self.save_reglist()
            self.save_commands()
        return self

    def save_results(self):
        self.results_path.write_text(json.dumps([asdict(row) for row in self.results]))

    def save_notes(self):
        self.notes_markdown_path.write_text(self.notes)

    def save_reglist(self):
        self.reg_list_path.write_text(self.reg_list.to_json_def())

    def save_commands(self):
        self.commands_path.write_text(json.dumps([cmd.to_dict() for cmd in self.commands]))

    def add_result(self, row: RawResult):
        self.results.append(row)
        self.results.sort(key=lambda x: x.address)

    def remove_result(self, index: int) -> RawResult | None:
        try:
            return self.results.pop(index)
        except IndexError:
            return None

    def replace_result(self, index: int, row: RawResult):
        try:
            self.results[index] = row
        except IndexError:
            pass

    def get_results_at_row(self, index: int) -> RawResult | None:
        try:
            return self.results[index]
        except IndexError:
            return None

    def get_results_index_of_by_addr(self, address: int | str) -> int:
        try:
            addr = int(address, 16) if isinstance(address, str) else address
            return [row.address for row in self.results].index(addr)
        except ValueError:
            return -1


class Projects:
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir
        self.projects_dir.mkdir(exist_ok=True)

        self.projects_file_path = self.projects_dir / "projects.json"
        if not self.projects_file_path.exists():
            projects_dirs = [d.name for d in self.projects_dir.iterdir() if d.is_dir()]
            self.projects_file_path.write_text(json.dumps(projects_dirs))

    def import_project_from_file(self, file_in: Path | str, app) -> str | None:
        from i2cc.project.projects_gui import project_name_picker

        with gzip.open(Path(file_in)) as f:
            data = json.loads(f.read().decode())
            project_name = data["project_name"]
            name_to_save_under = (
                project_name_picker(app, project_name) if project_name in self.list_projects() else project_name
            )
            if name_to_save_under is not None:
                project = self.new_project(name_to_save_under, override_existing=True)
                project.version_json_path.write_text(json.dumps(data["version"]))
                project.reg_list_path.write_text(json.dumps(data["regList"]))
                project.commands_path.write_text(json.dumps(data["commands"]))
                project.notes_markdown_path.write_text(data["notes"])
                return project.name
            else:
                return None

    def download_project_data_from_url(self, url: str) -> str | None:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return gzip.decompress(response.content).decode()
            else:
                return None
        except Exception as ex:
            print(ex)  # TODO: Emit message to show error dialog
            return None

    def import_project_from_data(self, txt: str, app) -> str | None:
        from i2cc.project.projects_gui import project_name_picker

        data = json.loads(txt)
        project_name = data["project_name"]
        name_to_save_under = (
            project_name_picker(app, project_name) if project_name in self.list_projects() else project_name
        )
        if name_to_save_under is not None:
            project = self.new_project(name_to_save_under, override_existing=True)
            project.version_json_path.write_text(json.dumps(data["version"]))
            project.reg_list_path.write_text(json.dumps(data["regList"]))
            project.commands_path.write_text(json.dumps(data["commands"]))
            project.notes_markdown_path.write_text(data["notes"])
            return project.name
        else:
            return None

    def list_projects(self) -> list[str]:
        return json.loads(self.projects_file_path.read_text())

    def new_project(self, name: str, override_existing: bool = False) -> Project:
        if not PROJECT_RE.match(name):
            raise ValueError("Project name must consist of only letters, numbers and underscore characters.")
        dir = self.projects_dir / name
        if dir.exists():
            if override_existing:
                shutil.rmtree(dir)
            else:
                raise RuntimeError(f"Project [{name}] already exists.")

        dir.mkdir(exist_ok=False)
        if not dir.exists():
            raise RuntimeError(f"Failed to create directory for project [{name}].")
        else:
            Project(name, dir).save()
            return self.open_project(name)

    def rename_project(self, old_name: str, new_name: str):
        open_projects_history = json.loads(self.projects_file_path.read_text())
        if old_name in open_projects_history:
            open_projects_history.remove(old_name)
        open_projects_history = [new_name] + open_projects_history
        self.projects_file_path.write_text(json.dumps(open_projects_history))

    def open_project(self, name: str) -> Project:
        dir = self.projects_dir / name
        if not dir.exists():
            raise RuntimeError(f"Project [{name}] does not exist.")
        else:
            # update open projects history which is sorted based on last opened status
            open_projects_history = json.loads(self.projects_file_path.read_text())
            if name in open_projects_history:
                open_projects_history.remove(name)
            open_projects_history = [name] + open_projects_history
            self.projects_file_path.write_text(json.dumps(open_projects_history))

            return Project(name, dir).load()

    def delete_project(self, name):
        dir = self.projects_dir / name
        if dir.exists():
            for f in dir.iterdir():
                f.unlink()

                # update opened projects history
                open_projects_history = json.loads(self.projects_file_path.read_text())
                if name in open_projects_history:
                    open_projects_history.remove(name)
                    self.projects_file_path.write_text(json.dumps(open_projects_history))

            dir.rmdir()
