import json
from abc import abstractmethod
from collections.abc import Callable
from enum import Enum, auto
from typing import Any, NamedTuple, override

import requests
from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
)
from pytide6 import Dialog, HBoxPanel, Label, Prompt, PushButton, RichTextLabel, VBoxLayout, W
from pytide6.inputs import LineEdit
from sprats.collections import Variable

from i2cc.app import App
from i2cc.gui_tools import (
    InTableSearchField,
    ListTableView,
    TableModelAllSelectableAndEnabled,
    TableModelWithFilterAction,
    TableModelWithOneColumn,
)


class RemoteProject(NamedTuple):
    name: str
    url: str


class ProjectsModel(
    TableModelWithOneColumn,
    TableModelAllSelectableAndEnabled,
    TableModelWithFilterAction,
):
    def __init__(self, project_names: list[str]):
        super().__init__()
        self.project_names = project_names
        self.project_names.sort()
        self.project_names_to_display = self.project_names.copy()
        self.project_names_raw = self.project_names_to_display.copy()

    def set_project_names(self, project_names: list[str]):
        self.beginResetModel()
        self.project_names = project_names
        self.project_names.sort()
        self.project_names_to_display = self.project_names.copy()
        self.project_names_raw = self.project_names_to_display.copy()
        self.endResetModel()

    def apply_filter(self, filter_text: str, post_filter_action: Callable[[], Any]):
        char_filter = list(filter_text)
        self.beginResetModel()
        try:
            self.project_names_to_display.clear()
            self.project_names_raw.clear()
            if char_filter == []:
                self.project_names_to_display = self.project_names.copy()
                self.project_names_raw = self.project_names_to_display.copy()
                return

            for project_name in self.project_names:
                j = 0
                new_label = ""
                for i in range(len(project_name)):
                    if j < len(char_filter) and char_filter[j].lower() == project_name[i].lower():
                        j += 1
                        new_label += f'<span style="background-color: pink; color: #000000;">{project_name[i]}</span>'
                    else:
                        new_label += project_name[i]
                if j == len(char_filter):
                    self.project_names_to_display.append(new_label)
                    self.project_names_raw.append(project_name)
        finally:
            self.endResetModel()
            post_filter_action()

    def headerData(self, section, orientation, /, role=...) -> Any:
        return None

    def rowCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return len(self.project_names_to_display)

    def columnCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return 1

    def data(self, index: QModelIndex | QPersistentModelIndex, /, role: int = ...) -> Any:
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return self.project_names_to_display[index.row()]
        else:
            return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled


class SimpleProjectDialogBase(Dialog):
    def __init__(
        self,
        app: App,
        window_title: str,
    ):
        super().__init__(app.main_window, windowTitle=window_title, modal=True)
        self.app = app

    def actions_widgets(self, ok_label: str, cancel_label: str = "Cancel") -> HBoxPanel:
        return HBoxPanel(
            [
                W(QLabel(), stretch=10),
                PushButton(ok_label, on_clicked=self.ok_action),
                PushButton(cancel_label, on_clicked=self.cancel_action),
            ]
        )

    @override
    def close(self) -> bool:
        self.app.update_project_selector_current_project(self.app.project.name)
        return super().close()

    @abstractmethod
    def ok_action(self):
        pass

    def cancel_action(self):
        self.close()

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        event_key = event.key()
        if event_key == Qt.Key.Key_Escape:
            self.cancel_action()
        else:
            super().keyPressEvent(event)


class OpenProjectDialog(SimpleProjectDialogBase):
    def __init__(self, app: App):
        super().__init__(app, window_title="Open Project")
        self.project_to_open: str | None = None
        self.projects_table = ListTableView(
            table_model=ProjectsModel(app.projects.list_projects()),
            pass_key_press_event=self.pass_key_press_event,
            on_double_clicked=lambda _: self.ok_action(),
            hide_horizontal_header=True,
        )

        self.search_field = InTableSearchField(
            table_view=self.projects_table,
            on_key_enter=lambda _: self.ok_action(),
            close_action=lambda: None,
        )

        self.setLayout(
            VBoxLayout([self.search_field, W(self.projects_table, stretch=1), self.actions_widgets("Open", "Cancel")])
        )

    def pass_key_press_event(self) -> Callable[[QKeyEvent], None]:
        def key_pressed(event: QKeyEvent) -> None:
            match event.key():
                case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                    self.ok_action()
                case _:
                    self.search_field.keyPressEvent(event)

        return key_pressed

    def ok_action(self):
        indexes: list[QModelIndex] = self.projects_table.selectedIndexes()
        if len(indexes) == 1:
            project_name_to_open = self.projects_table.table_model.project_names_raw[indexes[0].row()]
            self.project_to_open = project_name_to_open
            self.close()
            self.app.open_project(project_name_to_open)
            self.app.update_project_selector_current_project(self.app.project.name)


class NewProjectDialog(SimpleProjectDialogBase):
    def __init__(self, app: App):
        super().__init__(app, window_title="Create New Project")
        self.new_project_name = Variable[str]("")
        self.setLayout(
            VBoxLayout(
                [
                    Label("Create New Project"),
                    LineEdit("", min_width=100, reactive_variable=self.new_project_name),
                    self.actions_widgets("New Project"),
                ]
            )
        )

    def ok_action(self):
        try:
            self.app.create_new_project(self.new_project_name.value)
            self.app.update_project_selector_current_project(self.app.project.name)
            self.close()
        except Exception as ex:
            self.app.show_error(f"{ex}")


class OverrideAction(Enum):
    Override = auto()
    EnterUnderADifferentName = auto()
    Cancel = auto()


class OverrideProjectDialog(Prompt[OverrideAction]):
    def __init__(self, app: App, name: str):
        super().__init__(
            app.main_window, windowTitle="Override project on import?", default_value=OverrideAction.Cancel
        )

        def override():
            self.retval = OverrideAction.Override
            self.close()

        def different_name():
            self.retval = OverrideAction.EnterUnderADifferentName
            self.close()

        self.setLayout(
            VBoxLayout(
                [
                    Label(
                        f"Project under a name [{name}] already exits.\n"
                        f"Do you want to override it or import under a different name?"
                    ),
                    HBoxPanel(
                        [
                            W(QLabel(), stretch=10),
                            PushButton("Override", on_clicked=override),
                            PushButton("Import under a different name", on_clicked=different_name),
                            PushButton("Cancel", on_clicked=self.close),
                        ]
                    ),
                ]
            )
        )


class ImportNameProjectDialog(SimpleProjectDialogBase):
    def __init__(self, app: App, original_name: str):
        super().__init__(app, window_title="Import Project Under Name")
        self.project_name = Variable[str]("")
        self.setLayout(
            VBoxLayout(
                [
                    Label(
                        f'Project under name "{original_name}" already exists.\n'
                        "Please pick a new name under which to import project"
                    ),
                    LineEdit("", min_width=100, reactive_variable=self.project_name),
                    self.actions_widgets("Ok"),
                ]
            )
        )

    def ok_action(self):
        if self.project_name.value in self.app.projects.list_projects():
            self.app.show_error("Project under this name already exist. Please pick another name.")
        else:
            self.close()

    def cancel_action(self):
        self.project_name.value = ""
        super().cancel_action()


class SaveAsProjectDialog(SimpleProjectDialogBase):
    def __init__(self, app: App):
        super().__init__(app, window_title="Save Project As")
        self.new_project_name = Variable[str]("")
        self.setLayout(
            VBoxLayout(
                [
                    Label("Create copy of current project"),
                    LineEdit("", min_width=100, reactive_variable=self.new_project_name),
                    self.actions_widgets("New Project"),
                ]
            )
        )

    def ok_action(self):
        try:
            if self.new_project_name.value in self.app.projects.list_projects():
                self.app.show_error(
                    f"Project under name [{self.new_project_name.value}] already exist. Please pick another name."
                )
            else:
                self.app.project.save()
                self.app.create_copy_of_project(self.app.project.name, self.new_project_name.value)
                self.close()
                self.app.update_project_selector_current_project(self.app.project.name)
        except Exception as ex:
            self.app.show_error(f"{ex}")


class RenameProjectDialog(SimpleProjectDialogBase):
    def __init__(self, app: App):
        super().__init__(app, window_title="Rename Project")
        self.new_project_name = Variable[str]("")
        self.setLayout(
            VBoxLayout(
                [
                    Label("Rename current project to"),
                    LineEdit("", min_width=100, reactive_variable=self.new_project_name),
                    self.actions_widgets("Ok"),
                ]
            )
        )

    def ok_action(self):
        try:
            new_project_name = self.new_project_name.value.strip()
            if new_project_name == self.app.project.name:
                # project name did not change
                self.close()

            elif new_project_name in self.app.projects.list_projects():
                self.app.show_error(f"Project under name [{new_project_name}] already exist. Please pick another name.")

            else:
                self.app.project.save()
                old_project_name = self.app.project.rename(new_project_name)
                self.app.projects.rename_project(old_project_name, new_project_name)
                self.app.persistence.config.set_value("last_open_project", self.app.project.name)
                self.app.update_project_selector_current_project(self.app.project.name)
                self.close()
        except Exception as ex:
            self.app.show_error(f"{ex}")


class DeleteProjectDialog(SimpleProjectDialogBase):
    def __init__(self, app: App, project_to_delete: str):
        super().__init__(app, window_title="Delete Project?")
        self.project_to_delete = project_to_delete

        self.setLayout(
            VBoxLayout(
                [RichTextLabel(f"Delete Project [<b>{project_to_delete}</b>]?"), self.actions_widgets("Yes", "No")]
            )
        )

    def ok_action(self):
        self.app.delete_project(self.project_to_delete)
        self.close()
        self.app.update_project_selector_current_project(self.app.project.name)


def project_name_picker(app: App, name: str) -> str | None:
    match OverrideProjectDialog(app, name).prompt():
        case OverrideAction.Override:
            return name
        case OverrideAction.EnterUnderADifferentName:
            dialog = ImportNameProjectDialog(app, name).execute()
            return None if dialog.project_name.value.strip() == "" else dialog.project_name.value
        case _:  # Cancel action
            return None


class ProjectListFetcherThread(QThread):
    data_ready = Signal(list)

    def run(self):
        response = requests.get("https://api.github.com/repos/priimak/i2cc/contents?ref=projects")
        if response.status_code == 200:
            data = json.loads(response.text)
            projects = [
                RemoteProject(d["name"].removesuffix(".gz"), d["download_url"]) for d in data if d["type"] == "file"
            ]
            projects.sort(key=lambda rp: rp.name.lower())
            self.data_ready.emit(projects)


class ProjectDownloadThread(QThread):
    download_complete = Signal(str)

    def __init__(self, app: App, project_url_to_download: str, /):
        super().__init__()
        self.setObjectName("Hello")
        self.app = app
        self.project_url_to_download = project_url_to_download

    def run(self):
        self.download_complete.emit(self.app.projects.download_project_data_from_url(self.project_url_to_download))


class DownloadProjectDialog(Dialog):
    def __init__(self, app: App):
        super().__init__(app.main_window, windowTitle="Download project", modal=True)
        self.app = app
        self.project_to_open: str | None = None
        self.projects: dict[str, str] = dict()

        self.loading_label = Label("Loading...")
        self.projects_model = ProjectsModel([])
        self.projects_table = ListTableView(
            table_model=self.projects_model,
            pass_key_press_event=self.pass_key_press_event,
            on_double_clicked=lambda _: self.ok_action(),
            hide_horizontal_header=True,
        )
        self.projects_table.setVisible(False)

        self.search_field = InTableSearchField(
            table_view=self.projects_table,
            on_key_enter=lambda _: self.ok_action(),
            close_action=lambda: None,
        )
        self.search_field.setVisible(False)

        self.setLayout(
            VBoxLayout(
                [
                    self.loading_label,
                    self.search_field,
                    W(self.projects_table, stretch=1),
                    HBoxPanel(
                        [
                            W(QLabel(), stretch=10),
                            PushButton("Ok", on_clicked=self.ok_action),
                            PushButton("Cancel", on_clicked=self.close),
                        ]
                    ),
                ]
            )
        )

        self.worker = ProjectListFetcherThread()
        self.worker.data_ready.connect(self.update_projects_list)
        self.worker.start()

    @Slot(list)
    def update_projects_list(self, projects: list[RemoteProject]):
        self.projects_model.set_project_names([p.name for p in projects])
        for p in projects:
            self.projects[p.name] = p.url

        self.loading_label.setVisible(False)
        self.search_field.setVisible(True)
        self.projects_table.setVisible(True)
        self.adjustSize()

    @Slot()
    def download_complete(self, project_data: str):
        self.info_dialog.close()
        project_name = self.app.projects.import_project_from_data(project_data, self.app)
        self.app.open_project(project_name, save_currently_open=(project_name != self.app.project.name))

    def close(self, /) -> bool:
        self.worker.quit()
        return super().close()

    def pass_key_press_event(self) -> Callable[[QKeyEvent], None]:
        def key_pressed(event: QKeyEvent) -> None:
            match event.key():
                case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                    self.ok_action()
                case _:
                    self.search_field.keyPressEvent(event)

        return key_pressed

    def ok_action(self):
        indexes: list[QModelIndex] = self.projects_table.selectedIndexes()
        if len(indexes) == 1:
            self.info_dialog = QMessageBox(self.app.main_window)
            self.info_dialog.setIcon(QMessageBox.Icon.Information)
            self.info_dialog.setText("Downloading project ...")
            self.info_dialog.setModal(True)
            self.info_dialog.show()

            project_name_to_open = self.projects_table.table_model.project_names_raw[indexes[0].row()]
            self.project_to_open = project_name_to_open
            self.download_worker = ProjectDownloadThread(self.app, self.projects[project_name_to_open])
            self.download_worker.download_complete.connect(self.download_complete)
            self.download_worker.start()
        self.close()
