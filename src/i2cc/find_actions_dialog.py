from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6 import QtCore
from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QSize,
    Qt,
)
from PySide6.QtGui import QKeyEvent
from pytide6 import Dialog, Label, VBoxLayout

from i2cc.app import App
from i2cc.custom_commands.custom_command_editor import CustomCommandsEditor
from i2cc.dongles.dongle_selector_dialog import select_dongle
from i2cc.gui_tools import (
    InTableSearchField,
    ListTableView,
    TableModelAllSelectableAndEnabled,
    TableModelWithFilterAction,
    TableModelWithOneColumn,
    TableModelWithoutHeader,
    apply_filter_to_text,
)
from i2cc.project.projects_gui import (
    DeleteProjectDialog,
    DownloadProjectDialog,
    NewProjectDialog,
    OpenProjectDialog,
    RenameProjectDialog,
    SaveAsProjectDialog,
)
from i2cc.registers.reg_def_editor import NewRegDefDialog


@dataclass(slots=True, frozen=True)
class Action:
    name: str
    action: Callable[[App], Any]


ACTIONS = [
    Action("Create new project", lambda app: NewProjectDialog(app).exec()),
    Action("Define new custom action/command", lambda app: CustomCommandsEditor(app, cmd=None).exec()),
    Action("Define new register", lambda app: NewRegDefDialog(app).exec()),
    Action("Delete currently active project", lambda app: DeleteProjectDialog(app, app.project.name).exec()),
    Action("Delete custom action/command", None),
    Action("Download official project", lambda app: DownloadProjectDialog(app).exec()),
    Action("Download project from URL", None),
    Action("Edit custom action/command", None),
    Action("Execute custom action/command", None),
    Action("Exit/Quit application", lambda app: app.exit_application[0]()),
    Action("Export project into file", lambda app: app.export_project()),
    Action("Connect to a new/different dongle", select_dongle),
    Action("Import project from file", lambda app: app.import_project()),
    Action("Import official project from the internet", None),
    Action("Open project", lambda app: OpenProjectDialog(app).exec()),
    Action("Read register", None),
    Action("Rename project", lambda app: RenameProjectDialog(app).exec()),
    Action("Save currently open project under a different name", lambda app: SaveAsProjectDialog(app).exec()),
    Action("Write register", None),
]


class ActionsModel(
    TableModelWithoutHeader,
    TableModelWithOneColumn,
    TableModelAllSelectableAndEnabled,
    TableModelWithFilterAction,
):
    def __init__(
        self,
    ):
        super().__init__()
        self.actions_to_display = ACTIONS.copy()

    def rowCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return len(self.actions_to_display)

    def data(self, index: QModelIndex | QPersistentModelIndex, /, role: int = ...) -> Any:
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            return self.actions_to_display[index.row()].name
        else:
            return None

    def apply_filter(self, filter_text: str, post_filter_action: Callable[[], Any]):
        char_filter = list(filter_text)
        self.beginResetModel()
        self.actions_to_display.clear()
        if char_filter == []:
            self.actions_to_display = ACTIONS.copy()
            self.endResetModel()
            post_filter_action()
            return

        for action in ACTIONS:
            new_label = apply_filter_to_text(char_filter, action.name)
            if new_label is not None:
                self.actions_to_display.append(Action(new_label, action.action))

        self.endResetModel()
        post_filter_action()


class FindActionDialog(Dialog):
    def __init__(self, app: App):
        super().__init__(app.main_window, windowTitle="Find Action", modal=True)
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Window)
        self.app = app
        self.actions_table = ListTableView(
            table_model=ActionsModel(),
            pass_key_press_event=self.pass_key_press_event,
            on_double_clicked=self.on_actions_table_double_clicked,
            hide_horizontal_header=True,
        )
        self.search_field = InTableSearchField(
            table_view=self.actions_table,
            on_key_enter=lambda index: self.actions_table.table_model.actions_to_display[index.row()].action(self.app),
            close_action=self.close,
        )
        self.setLayout(VBoxLayout([Label("Find Action"), self.search_field, self.actions_table]))
        self.search_field.setFocus()
        screen_dim: QSize = app.q_application.primaryScreen().size()
        self.resize(int(screen_dim.width() / 2), int(screen_dim.height() / 3))

    def pass_key_press_event(self) -> Callable[[QKeyEvent], None]:
        return self.search_field.keyPressEvent

    def on_actions_table_double_clicked(self, index: QModelIndex):
        self.close()
        self.actions_table.table_model.actions_to_display[index.row()].action(self.app)
