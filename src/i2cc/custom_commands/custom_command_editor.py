import dataclasses
import re
import traceback
from collections.abc import Callable

from PySide6 import QtCore
from PySide6.QtGui import QKeyEvent, Qt, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit
from pytide6 import Dialog, HBoxPanel, PushButton, VBoxLayout, W
from pytide6.frame import HorizonalLine
from pytide6.inputs import LineEdit
from sprats.collections import Variable

from i2cc.app import App
from i2cc.custom_commands.find_register_dialog import FindRegisterDialog
from i2cc.project.project import CustomCommand

COMMENT_REGEX = re.compile(r"^(\s*)#\s?")
NO_COMMENT_REGEX = re.compile(r"^(\s*)")


class CodeEditor(QPlainTextEdit):
    space_key_event = QKeyEvent(QtCore.QEvent.Type.KeyPress, Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.NoModifier, " ")

    def __init__(self, app: App, save_command: Callable[[], None]):
        super().__init__()
        self.app = app
        self.save_command = save_command
        self.setStyleSheet("QTextEdit { font-family: 'Monospace'; }")
        char_width = self.fontMetrics().height()
        self.setMinimumHeight(char_width * 25)

    def keyPressEvent(self, event: QKeyEvent, /) -> None:
        key = event.key()
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if key == Qt.Key.Key_Tab:
                super().keyPressEvent(CodeEditor.space_key_event)
                super().keyPressEvent(CodeEditor.space_key_event)
                super().keyPressEvent(CodeEditor.space_key_event)
                super().keyPressEvent(CodeEditor.space_key_event)
                return

            if key == Qt.Key.Key_Y and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
                # delete line on Ctrl-y
                c = self.textCursor()
                c.select(QTextCursor.SelectionType.LineUnderCursor)
                c.removeSelectedText()
                c.deleteChar()
                self.setTextCursor(c)
                return

            if (
                key == Qt.Key.Key_Up
                and event.modifiers()
                == QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier
            ):
                c = self.textCursor()
                at_column = c.columnNumber()
                c.select(QTextCursor.SelectionType.LineUnderCursor)
                line_to_move = c.selection().toPlainText()
                c.removeSelectedText()
                c.deleteChar()
                c.movePosition(QTextCursor.MoveOperation.Up)
                c.movePosition(QTextCursor.MoveOperation.StartOfLine)
                c.insertText(line_to_move + "\n")
                c.movePosition(QTextCursor.MoveOperation.Up)
                c.movePosition(QTextCursor.MoveOperation.StartOfLine)
                c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, at_column)
                self.setTextCursor(c)
                return

            if (
                key == Qt.Key.Key_Down
                and event.modifiers()
                == QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier
            ):
                c = self.textCursor()
                at_column = c.columnNumber()
                c.select(QTextCursor.SelectionType.LineUnderCursor)
                line_to_move = c.selection().toPlainText()
                c.removeSelectedText()
                c.deleteChar()
                c.movePosition(QTextCursor.MoveOperation.Down)
                c.movePosition(QTextCursor.MoveOperation.StartOfLine)
                c.insertText(line_to_move + "\n")
                c.movePosition(QTextCursor.MoveOperation.Up)
                c.movePosition(QTextCursor.MoveOperation.StartOfLine)
                c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, at_column)
                self.setTextCursor(c)
                return

            if key == Qt.Key.Key_D and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
                # duplicate line
                c = self.textCursor()
                at_column = c.columnNumber()
                c.select(QTextCursor.SelectionType.LineUnderCursor)
                line_str = c.selection().toPlainText()
                c.movePosition(QTextCursor.MoveOperation.EndOfLine)
                c.insertText(f"\n{line_str}")
                c.movePosition(QTextCursor.MoveOperation.StartOfLine)
                c.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, at_column)
                self.setTextCursor(c)
                return

            if key == Qt.Key.Key_Slash and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
                # (Un)Comment out line or selection of lines on Ctrl-/
                c = self.textCursor()
                one_line_comment = False
                if not c.hasSelection():
                    c.select(QTextCursor.SelectionType.LineUnderCursor)
                    one_line_comment = True

                selection_start = c.selectionStart()
                selection_end = c.selectionEnd()

                c.setPosition(selection_start)
                c.movePosition(QTextCursor.MoveOperation.StartOfLine)
                start_position = c.position()
                c.setPosition(selection_end)
                c.movePosition(QTextCursor.MoveOperation.EndOfLine)
                end_position = c.position()
                c.setPosition(start_position)
                c.setPosition(end_position, QTextCursor.MoveMode.KeepAnchor)

                lines: list[str] = c.selectedText().splitlines()
                new_lines = []
                for line in lines:
                    comment_match = COMMENT_REGEX.match(line)
                    if comment_match:
                        new_lines.append(re.sub(COMMENT_REGEX, r"\1", line))
                    else:
                        new_lines.append(re.sub(NO_COMMENT_REGEX, r"\1# ", line))

                new_text_block = "\n".join(new_lines)
                c.beginEditBlock()
                c.removeSelectedText()
                c.insertText(new_text_block)
                c.endEditBlock()

                if one_line_comment:
                    c.movePosition(QTextCursor.MoveOperation.Down)
                else:
                    # try to keep selection; it will be distorted a bit most of the time though
                    c.setPosition(start_position)
                    c.setPosition(
                        min(start_position + len(new_text_block), self.document().characterCount() - 1),
                        QTextCursor.MoveMode.KeepAnchor,
                    )

                self.setTextCursor(c)
                return

            if (
                key in [Qt.Key.Key_Enter, Qt.Key.Key_Return]
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            ):
                self.save_command()
                return

        super().keyPressEvent(event)

        if key == Qt.Key.Key_Period and self.textCursor().block().text()[0 : self.textCursor().columnNumber()].endswith(
            "dut."
        ):
            # show popup selector for registers and fields
            pos = self.cursorRect().topLeft()
            pos = self.viewport().mapToGlobal(pos)
            dialog = FindRegisterDialog(self, self.app, self.insertPlainText)
            dialog.move(pos)
            dialog.exec()


class CustomCommandsEditor(Dialog):
    def __init__(self, app: App, cmd: CustomCommand | None):
        super().__init__(app.main_window, windowTitle="Edit/Create Custom Command", modal=True)
        self.app = app
        self.original_cmd = None if cmd is None else dataclasses.replace(cmd)

        self.command_label = Variable("" if cmd is None else cmd.label)
        self.code_editor = CodeEditor(app, self.save_command)
        if cmd is not None:
            self.code_editor.appendPlainText(cmd.source_code)

        self.setLayout(
            VBoxLayout(
                [
                    LineEdit(
                        reactive_variable=self.command_label,
                        with_min_width_for_text=(" " * 200),
                        on_key_enter=lambda _: self.code_editor.setFocus(),
                    ),
                    W(self.code_editor, stretch=1),
                    HorizonalLine(),
                    HBoxPanel(
                        [
                            W(stretch=1),
                            PushButton("Ok", on_clicked=self.save_command, auto_default=False),
                            PushButton("Cancel", on_clicked=self.close, auto_default=False),
                        ],
                        margins=0,
                    ),
                ]
            )
        )

    def save_command(self):
        code = self.code_editor.toPlainText()
        try:
            command_label = self.command_label.value.strip()
            if command_label == "":
                self.app.show_error("Command must have a label.")
                return

            if (
                self.original_cmd is None
                or (self.original_cmd is not None and command_label != self.original_cmd.label)
            ) and command_label in self.app.project.commands_by_label:
                self.app.show_error("Command with this name already exist. Please pick another name.")
                return

            new_cmd = CustomCommand(
                label=command_label,
                source_code=code,
                compiled_code=compile(code, "<str>", "exec"),
            )
            if self.original_cmd is None:
                self.app.project.add_custom_command(new_cmd)
            else:
                self.app.project.update_custom_command(self.original_cmd, new_cmd)

            self.close()
            self.app.request_commands_reload(True)  # True requests to keep current selection
        except Exception as ex:
            tb_lines = traceback.format_exception(type(ex), ex, ex.__traceback__)
            x = "".join(tb_lines[2:])
            self.app.show_error(str(x))


# if __name__ == '__main__':
#     import tree_sitter_python as tspython
#     from tree_sitter import Language, Parser
#
#     PY_LANGUAGE = Language(tspython.language())
#     parser = Parser(PY_LANGUAGE)
#     tree = parser.parse(
#         bytes(
#             """
# if ctx.init_done is not None:
#     print("Power-on init sequence was already done once")
#     exit()
#
# read(dut.CHIP_ID)
# read(dut.STATUS)
# read(dut.INT_STATUS)
#
# if dut.CHIP_ID.chip_id == 0:
#     print("Init failed. CHIP_ID is 0")
#
# elif dut.STATUS.status_nvm_rdy != 1:
#     print(f"Init failed. STATUS.status_nvm_rdy is {dut.STATUS.status_nvm_rdy}")
#
# elif dut.STATUS.status_nvm_err != 0:
#     print(f"Init failed. STATUS.status_nvm_err is {dut.STATUS.status_nvm_err}")
#
# elif dut.INT_STATUS.por != 1:
#     print(f"Init failed. INT_STATUS.por is {dut.INT_STATUS.por}")
#
# else:
#     print("Init success")
#     ctx.init_done = True
#     """,
#             "utf8",
#         )
#     )
#     root_node = tree.root_node
#     print(root_node)
#     cursor = root_node.walk()
#     print(cursor)
#
