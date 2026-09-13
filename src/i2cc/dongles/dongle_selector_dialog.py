import sys

import serial.tools.list_ports as slp
from pytide6 import ComboBox, HBoxPanel, Label, Prompt, PushButton, VBoxLayout, W
from sprats.collections import Variable

from i2cc.app import App
from i2cc.dongles.dongles import SUPPORTED_DONGLES, SUPPORTED_DONGLES_DICT


class DongleSelectorDialog(Prompt[bool]):
    def __init__(self, app: App):
        super().__init__(app.main_window, windowTitle="Select dongle to connect to", default_value=False)

        ports = [p.device for p in slp.comports() if SUPPORTED_DONGLES[0].comp_port_filter[sys.platform](p)]
        if ports == []:
            ports = [""]

        self.com_ports = ComboBox(items=ports, current_selection=ports[0])

        def update_com_ports_combo_box(make_and_model: str | None):
            ports = [
                p.device
                for p in slp.comports()
                if SUPPORTED_DONGLES_DICT[make_and_model].comp_port_filter[sys.platform](p)
            ]
            if ports == []:
                ports = [""]
            self.com_ports.clear()
            self.com_ports.addItems(ports)
            self.com_ports.setCurrentText(ports[0])

        self.dongle_id = Variable(
            SUPPORTED_DONGLES[0].make_and_model,
            valid_values=[a.make_and_model for a in SUPPORTED_DONGLES],
            on_value_change=update_com_ports_combo_box,
        )

        def ok():
            com_port = self.com_ports.currentText()
            if com_port == "":
                app.show_error("You cannot select dongle without COM port it is deemed to be connected")
            else:
                try:
                    app.i2c_master.value = SUPPORTED_DONGLES_DICT[self.dongle_id.value].cons(com_port, app.i2c_logger)
                    app.persistence.config.set_value(
                        "last_selected_device", {"make_and_model": self.dongle_id.value, "port": com_port}
                    )
                    self.retval = True
                    self.close()
                except Exception as ex:
                    app.show_error(str(ex))

        self.setLayout(
            VBoxLayout(
                [
                    HBoxPanel([Label("Make and Model"), ComboBox(reactive_variable=self.dongle_id)]),
                    HBoxPanel([Label("COM Port"), self.com_ports]),
                    HBoxPanel(
                        [
                            W(stretch=1),
                            PushButton("Ok", on_clicked=ok, auto_default=True),
                            PushButton("Cancel", on_clicked=self.close, auto_default=False),
                        ]
                    ),
                ]
            )
        )


def select_dongle(app: App) -> bool:
    return DongleSelectorDialog(app).prompt()
