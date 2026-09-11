from abc import abstractmethod
from collections.abc import Callable
from typing import Any, override

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QLabel,
    QTableWidget,
)
from pytide6 import Dialog, HBoxPanel, Label, PushButton, RichTextLabel, VBoxLayout, W
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


class ProjectDialog(Dialog):
    def __init__(self, parent, title: str) -> None:
        super().__init__(parent, windowTitle=title, modal=True)
        self.layout = VBoxLayout()
        self.setLayout(self.layout)
        self.layout.addWidget(Label(title))
        self.projects = QTableWidget(self)


class ProjectsModel(
    TableModelWithOneColumn,
    TableModelAllSelectableAndEnabled,
    TableModelWithFilterAction,
):
    def __init__(self, app: App):
        super().__init__()
        self.app = app
        self.project_names = app.projects.list_projects()
        self.project_names.sort()
        self.project_names_to_display = self.project_names.copy()
        self.project_names_raw = self.project_names_to_display.copy()

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
        label = RichTextLabel("Open Project")

        def selection_filter_changed(char_filter: list[str]):
            if char_filter == []:
                label.setText("Open Project")
            else:
                label.setText(
                    'Open Project [<span style="background-color: yellow;">' + (",".join(char_filter)) + "</span>]"
                )

        self.projects_table = ListTableView(
            table_model=ProjectsModel(app),
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


class ImportNameProjectDialog(SimpleProjectDialogBase):
    def __init__(self, app: App, original_name: str):
        super().__init__(app, window_title="Import Project Under Name")
        self.project_name = Variable[str]("")
        self.setLayout(
            VBoxLayout(
                [
                    Label(
                        f'Project under name "{original_name}" already exists.\n'
                        "Please pick new name under which to import project"
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
