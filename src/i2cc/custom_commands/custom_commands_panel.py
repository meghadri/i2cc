import io
import traceback
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import Any

from i2c_api import I2CError, I2CTransaction
from PySide6 import QtCore
from PySide6.QtCore import QByteArray, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLabel, QMessageBox, QTextEdit
from pytide6 import HBoxPanel, Label, Menu, PushButton, Splitter, VBoxPanel, W
from rgscore import RLinkI2C, S, U
from sprats.collections import Variable

from i2cc.app import App
from i2cc.custom_commands.code_preview_widget import CodePreviewWidget
from i2cc.custom_commands.custom_command_editor import CustomCommandsEditor
from i2cc.custom_commands.user_prompt import EvalExit, mk_prompt_user
from i2cc.gui_tools import (
    InTableSearchField,
    ListTableView,
    TableModelAllSelectableAndEnabled,
    TableModelWithFilterAction,
    TableModelWithOneColumn,
    apply_filter_to_text,
)
from i2cc.project.project import CustomCommand

title_labels_css = "background-color: #404040; color: white; font-weight: bold;"


@dataclass
class CommandLabelAndId:
    label: str
    id: str


class CommandsListModel(
    TableModelWithOneColumn,
    TableModelAllSelectableAndEnabled,
    TableModelWithFilterAction,
):
    def __init__(self, app: App, code_preview_widget: CodePreviewWidget):
        super().__init__()
        self.app = app
        self.code_preview_widget = code_preview_widget
        self.commands_to_display: list[CommandLabelAndId] = self.mk_commands_to_display()

    def update_based_on_command_table_selection_change(
        self, selection: QtCore.QItemSelection, _: QtCore.QItemSelection
    ):
        selected_indexes = selection.indexes()
        if selected_indexes == []:
            self.code_preview_widget.setText("")
        else:
            selected_row = selected_indexes[0].row()
            cmd = self.app.project.get_custom_command_by_label(self.commands_to_display[selected_row].id)
            if cmd is not None:
                self.code_preview_widget.setText(cmd.source_code)

    def mk_commands_to_display(self) -> list[CommandLabelAndId]:
        return [CommandLabelAndId(c.label, c.label) for c in self.app.project.commands]

    def regenerate_commands_to_display(self):
        self.commands_to_display = self.mk_commands_to_display()

    def headerData(self, section, orientation, /, role=...) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            return None
        else:
            return super().headerData(section, orientation, role)

    def rowCount(self, /, parent: QModelIndex | QPersistentModelIndex = ...) -> int:
        return len(self.commands_to_display)

    def data(self, index: QModelIndex | QPersistentModelIndex, /, role: int = ...) -> Any:
        if index.isValid() and role == Qt.ItemDataRole.DisplayRole:
            cmd = self.commands_to_display[index.row()]
            return cmd.label if index.column() == 0 else None
        else:
            return None

    def apply_filter(self, filter_text: str, post_filter_action: Callable[[], Any]):
        char_filter = list(filter_text)
        self.beginResetModel()
        try:
            self.commands_to_display.clear()
            commands_to_display_input = self.mk_commands_to_display()

            if char_filter == []:
                self.commands_to_display = commands_to_display_input
            else:
                for command in commands_to_display_input:
                    new_command_label = apply_filter_to_text(char_filter, command.label)
                    if new_command_label is not None:
                        self.commands_to_display.append(CommandLabelAndId(new_command_label, command.label))
        finally:
            self.endResetModel()
            post_filter_action()


class ResultsText(QTextEdit):
    def __init__(self, app: App):
        super().__init__()
        self.app = app
        self.setStyleSheet("QTextEdit { font-family: 'Monospace'; }")


class CustomCommandsPanel(VBoxPanel):
    def __init__(self, app: App):
        super().__init__(background_color="lightyellow", margins=(7, 7, 7, 0))
        self.app = app
        self.app.request_commands_reload = self.request_commands_reload

        self.code_preview_widget = CodePreviewWidget()
        commands_table_model = CommandsListModel(app, self.code_preview_widget)
        self.commands_table = ListTableView(
            table_model=commands_table_model,
            pass_key_press_event=self.pass_key_press_event,
            on_double_clicked=self.on_commands_table_double_clicked,
            hide_horizontal_header=True,
        )
        self.commands_table.selectionModel().selectionChanged.connect(
            commands_table_model.update_based_on_command_table_selection_change
        )

        self.context_menu = Menu(
            parent=self,
            actions=[
                ("Run", self.eval_selected_command),
                ("Edit", self.edit_selected_command),
                ("Delete", self.delete_selected_command),
            ],
        )
        self.commands_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.commands_table.customContextMenuRequested.connect(
            lambda pos: self.context_menu.popup(self.commands_table.viewport().mapToGlobal(pos))
        )

        self.results_text = ResultsText(app)
        self.app.append_custom_commands_log_stdout = self.results_text.append

        self.search_field = InTableSearchField(
            table_view=self.commands_table,
            on_key_enter=lambda _: self.eval_selected_command(),
            close_action=lambda: None,
        )

        self.results_and_preview_splitter = Splitter(
            Qt.Orientation.Vertical,
            childrenCollapsible=False,
            handleWidth=3,
            widgets=[
                VBoxPanel(
                    [
                        HBoxPanel(
                            [(Label(" Output Console ", css=title_labels_css)), W(stretch=1)],
                            margins=0,
                        ),
                        self.results_text,
                    ],
                    margins=0,
                    spacing=0,
                ),
                VBoxPanel(
                    [
                        HBoxPanel(
                            [(Label(" Code Preview ", css=title_labels_css)), W(stretch=1)],
                            margins=0,
                        ),
                        self.code_preview_widget,
                    ],
                    margins=(0, 10, 0, 0),
                    spacing=0,
                ),
            ],
            margins=0,
        )
        self.custom_commands_main_splitter = Splitter(
            Qt.Orientation.Horizontal,
            childrenCollapsible=False,
            handleWidth=8,
            widgets=[
                VBoxPanel(
                    [
                        HBoxPanel(
                            [(Label(" Commands/Actions ", css=title_labels_css)), W(stretch=1)],
                            margins=0,
                        ),
                        self.commands_table,
                    ],
                    margins=0,
                    spacing=0,
                ),
                self.results_and_preview_splitter,
            ],
        )

        self.withWidgets(
            HBoxPanel(
                widgets=[
                    PushButton("Define new command", on_clicked=self.define_new_command),
                    PushButton("Edit selected command", on_clicked=self.edit_selected_command),
                    PushButton("Delete selected command", on_clicked=self.delete_selected_command),
                    QLabel("        "),
                    PushButton("Run command", on_clicked=self.eval_selected_command),
                    W(stretch=1),
                ],
                margins=0,
            ),
            self.search_field,
            W(self.custom_commands_main_splitter, stretch=2),
        )

    def pass_key_press_event(self) -> Callable[[QKeyEvent], None]:
        def key_pressed(event: QKeyEvent) -> None:
            match event.key():
                case Qt.Key.Key_Return | Qt.Key.Key_Enter:
                    self.eval_selected_command()
                case Qt.Key.Key_Delete:
                    self.delete_selected_command()
                case _:
                    self.search_field.keyPressEvent(event)

        return key_pressed

    def eval_selected_command(self):
        selected_indexes = self.commands_table.selectedIndexes()
        if selected_indexes is None or len(selected_indexes) == 0:
            return
        try:
            selected_row = selected_indexes[0].row()

            command_label = self.commands_table.table_model.commands_to_display[selected_row].id
            for cmd in self.app.project.commands:
                if cmd.label == command_label:
                    link = RLinkI2C(self.app.i2c, self.app.device_address)

                    def mk_link_provider(lnk):
                        def provider():
                            return lnk

                        return provider

                    def exit_eval():
                        raise EvalExit()

                    attrs = {}
                    for r in self.app.project.reg_list.registers:
                        attrs[r.name] = r.mk_embedding_class(mk_link_provider(link), auto_sync=False)()
                    dut_cls = type("DUT", (), attrs)
                    gg = {
                        "read": lambda r: r._read(),
                        "write": lambda r: r._write(),
                        "dut": dut_cls(),
                        "ctx": self.app.project.commands_context,
                        "i2c": I2CTransaction(self.app.i2c, default_device_address=self.app.device_address),
                        "prompt_user": mk_prompt_user(cmd.label),
                        "Variable": Variable,
                        "exit": exit_eval,
                        "U": U,
                        "S": S,
                        "__command_name__": str(command_label),
                        "__device_address__": self.app.device_address,
                        "__project_name__": self.app.project.name,
                    }
                    out_buffer = io.StringIO()
                    try:
                        with redirect_stdout(out_buffer), redirect_stderr(out_buffer):
                            eval(cmd.compiled_code, gg)
                    finally:
                        log_str = out_buffer.getvalue().rstrip()
                        if log_str != "":
                            self.app.append_custom_commands_log_stdout(log_str)

        except EvalExit:
            pass
        except Exception as ex:
            if isinstance(ex, I2CError):
                self.app.show_error(str(ex))
            else:
                tb_lines = traceback.format_exception(type(ex), ex, ex.__traceback__)
                x = "".join(tb_lines[2:])
                self.app.show_error(str(x))

    def on_commands_table_double_clicked(self, index: QModelIndex):
        self.eval_selected_command()

    def define_new_command(self):
        CustomCommandsEditor(self.app, cmd=None).exec()

    def get_selected_command(self) -> tuple[CustomCommand, int] | None:
        selected_row = self.get_selected_row()
        if selected_row == -1:
            return None
        else:
            label = self.commands_table.table_model.commands_to_display[selected_row].id
            return self.app.project.get_custom_command_by_label(label), selected_row

    def delete_selected_command(self):
        match self.get_selected_command():
            case (cmd, row):
                ret = QMessageBox.question(
                    self.app.main_window,
                    "Delete custom command?",
                    "Please confirm that you want to delete this command?",
                    QMessageBox.StandardButton.Yes,
                    QMessageBox.StandardButton.No,
                )
                if ret == QMessageBox.StandardButton.Yes:
                    self.commands_table.table_model.beginResetModel()
                    self.app.project.delete_custom_command(cmd.label)
                    self.commands_table.table_model.regenerate_commands_to_display()
                    self.commands_table.table_model.endResetModel()
                    self.commands_table.selectRow(min(self.commands_table.table_model.rowCount() - 1, row))

    def edit_selected_command(self):
        match self.get_selected_command():
            case (cmd, _):
                CustomCommandsEditor(self.app, cmd).exec()

    def get_selected_row(self) -> int:
        selected_indexes = self.commands_table.selectedIndexes()
        if selected_indexes is None or len(selected_indexes) == 0:
            return -1
        else:
            return selected_indexes[0].row()

    def request_commands_reload(self, keep_selection: bool):
        self.code_preview_widget.clear()
        selected_row = self.get_selected_row()
        self.commands_table.table_model.beginResetModel()
        self.commands_table.table_model.regenerate_commands_to_display()
        self.commands_table.table_model.endResetModel()
        if keep_selection:
            self.commands_table.selectRow(selected_row)
        else:
            # keep_selection is False when project just opens, for example when we are switching between projects
            # or on start up when previously opened project is loaded. Thus, we use this flag to see if there is a
            # command called __start__ and if it does, then evaluate it.
            self.search_field.clear()
            self.results_text.clear()
            for row, c in enumerate(self.commands_table.table_model.commands_to_display):
                if c.id == "__start__":
                    self.commands_table.selectRow(row)
                    self.eval_selected_command()
                    return

    def save_state(self):
        self.app.persistence.state.set_value(
            "custom_commands_main_splitter_state",
            self.custom_commands_main_splitter.saveState()
            .toBase64(QByteArray.Base64Option.Base64Encoding)
            .data()
            .decode("utf-8"),
        )

        self.app.persistence.state.set_value(
            "results_and_preview_splitter_state",
            self.results_and_preview_splitter.saveState()
            .toBase64(QByteArray.Base64Option.Base64Encoding)
            .data()
            .decode("utf-8"),
        )

    def restore(self):
        spl_state = self.app.persistence.state.get_value("custom_commands_main_splitter_state")
        if spl_state is not None:
            self.custom_commands_main_splitter.restoreState(QByteArray.fromBase64(spl_state.encode("utf-8")))

        spl_state = self.app.persistence.state.get_value("results_and_preview_splitter_state")
        if spl_state is not None:
            self.results_and_preview_splitter.restoreState(QByteArray.fromBase64(spl_state.encode("utf-8")))
