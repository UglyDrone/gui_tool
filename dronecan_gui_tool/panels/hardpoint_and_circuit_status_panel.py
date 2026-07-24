#
# Copyright (C) 2026 DroneCAN Development Team <dronecan.org>
#
# This software is distributed under the terms of the MIT License.
#

import dronecan
from functools import partial
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QDialog, QSpinBox, QComboBox, QPlainTextEdit, QGroupBox, QGridLayout
from PyQt6.QtCore import Qt, QTimer
from logging import getLogger
from ..widgets import make_icon_button, get_icon, get_monospace_font

__all__ = 'PANEL_NAME', 'spawn', 'get_icon'

PANEL_NAME = 'Hardpoints and CircuitStatus Panel'

logger = getLogger(__name__)

_singleton = None


class HardpointsAndCircuitStatusPanel(QDialog):
    def __init__(self, parent, node):
        super(HardpointsAndCircuitStatusPanel, self).__init__(parent)
        self.setWindowTitle('Hardpoints and CircuitStatus Control & Monitor')
        self.setAttribute(Qt.WA_DeleteOnClose)

        self._node = node

        # Main Layout
        layout = QVBoxLayout(self)

        # ---------------------------------------------------------
        # Control Group Box (Relay/Hardpoint Controls)
        # ---------------------------------------------------------
        control_group = QGroupBox('Relay / Hardpoint Control', self)
        control_layout = QVBoxLayout()

        # Hardpoint ID field
        hp_id_layout = QHBoxLayout()
        hp_id_layout.addWidget(QLabel('Hardpoint ID:', self))
        self._hardpoint_id = QSpinBox(self)
        self._hardpoint_id.setMinimum(0)
        self._hardpoint_id.setMaximum(255)
        self._hardpoint_id.setValue(0)
        hp_id_layout.addWidget(self._hardpoint_id)
        hp_id_layout.addStretch()
        control_layout.addLayout(hp_id_layout)

        # Command / State field
        state_layout = QHBoxLayout()
        state_layout.addWidget(QLabel('State / Command:', self))
        self._state_combo = QComboBox(self)
        self._state_combo.addItem('0 - Release / OFF', 0)
        self._state_combo.addItem('1 - Hold / ON', 1)
        self._state_combo.addItem('Custom...', -1)
        self._state_combo.currentIndexChanged.connect(self._on_state_combo_changed)
        state_layout.addWidget(self._state_combo)

        self._custom_val = QSpinBox(self)
        self._custom_val.setMinimum(0)
        self._custom_val.setMaximum(65535)
        self._custom_val.setValue(0)
        self._custom_val.setVisible(False)
        state_layout.addWidget(self._custom_val)
        state_layout.addStretch()
        control_layout.addLayout(state_layout)

        # Send Button
        self._send_button = make_icon_button('fa6s.paper-plane', 'Send command', self, text='Send Command', on_clicked=self._do_send)
        control_layout.addWidget(self._send_button)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # ---------------------------------------------------------
        # Monitoring Group Box (CircuitStatus updates)
        # ---------------------------------------------------------
        monitor_group = QGroupBox('Circuit Status Monitor', self)
        monitor_layout = QGridLayout()

        # Headers
        monitor_layout.addWidget(QLabel('<b>Circuit</b>'), 0, 0)
        monitor_layout.addWidget(QLabel('<b>Voltage</b>'), 0, 1)
        monitor_layout.addWidget(QLabel('<b>Current</b>'), 0, 2)
        monitor_layout.addWidget(QLabel('<b>Power</b>'), 0, 3)
        monitor_layout.addWidget(QLabel('<b>Status / Errors</b>'), 0, 4)

        # Circuits setup
        self._circuit_rows = {}
        circuit_names = {
            1: 'Circuit 1 (5V)',
            2: 'Circuit 2 (12V)',
            3: 'Circuit 3 (48V)'
        }

        for idx, (cid, name) in enumerate(circuit_names.items(), start=1):
            lbl_name = QLabel(name, self)
            lbl_volt = QLabel('NC', self)
            lbl_curr = QLabel('NC', self)
            lbl_pwr = QLabel('NC', self)
            lbl_err = QLabel('NC', self)

            # Monospace values for clean alignment
            font = get_monospace_font()
            lbl_volt.setFont(font)
            lbl_curr.setFont(font)
            lbl_pwr.setFont(font)
            lbl_err.setFont(font)

            monitor_layout.addWidget(lbl_name, idx, 0)
            monitor_layout.addWidget(lbl_volt, idx, 1)
            monitor_layout.addWidget(lbl_curr, idx, 2)
            monitor_layout.addWidget(lbl_pwr, idx, 3)
            monitor_layout.addWidget(lbl_err, idx, 4)

            self._circuit_rows[cid] = {
                'voltage': lbl_volt,
                'current': lbl_curr,
                'power': lbl_pwr,
                'error': lbl_err,
                'last_update': 0
            }

        monitor_group.setLayout(monitor_layout)
        layout.addWidget(monitor_group)

        # Generated message viewer
        layout.addWidget(QLabel('Last Sent Message:', self))
        self._msg_viewer = QPlainTextEdit(self)
        self._msg_viewer.setReadOnly(True)
        self._msg_viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._msg_viewer.setFont(get_monospace_font())
        self._msg_viewer.setMaximumHeight(100)
        layout.addWidget(self._msg_viewer)

        self.setLayout(layout)
        self.resize(550, 450)

        # Register DroneCAN handler for CircuitStatus
        self._handlers = [
            self._node.add_handler(dronecan.uavcan.equipment.power.CircuitStatus, self._on_circuit_status)
        ]

        # Timer to check for offline/stale status
        self._stale_timer = QTimer(self)
        self._stale_timer.timeout.connect(self._check_stale_circuits)
        self._stale_timer.start(1000)

    def _on_circuit_status(self, event):
        import time
        msg = event.message
        cid = msg.circuit_id

        if cid in self._circuit_rows:
            row = self._circuit_rows[cid]
            row['last_update'] = time.time()
            
            # Format voltage, current, power
            v = msg.voltage
            i = msg.current
            p = v * i
            
            row['voltage'].setText(f'{v:6.2f} V')
            row['current'].setText(f'{i:6.2f} A')
            row['power'].setText(f'{p:6.2f} W')

            # Parse error flags
            errs = []
            flags = msg.error_flags
            if flags & dronecan.uavcan.equipment.power.CircuitStatus.ERROR_FLAG_OVERVOLTAGE:
                errs.append('OVER_V')
            if flags & dronecan.uavcan.equipment.power.CircuitStatus.ERROR_FLAG_UNDERVOLTAGE:
                errs.append('UNDER_V')
            if flags & dronecan.uavcan.equipment.power.CircuitStatus.ERROR_FLAG_OVERCURRENT:
                errs.append('OVER_C')
            if flags & dronecan.uavcan.equipment.power.CircuitStatus.ERROR_FLAG_UNDERCURRENT:
                errs.append('UNDER_C')

            if errs:
                row['error'].setText(', '.join(errs))
                row['error'].setStyleSheet('color: red; font-weight: bold;')
            else:
                row['error'].setText('OK')
                row['error'].setStyleSheet('color: green;')

    def _check_stale_circuits(self):
        import time
        now = time.time()
        for cid, row in self._circuit_rows.items():
            if row['last_update'] == 0:
                continue
            if now - row['last_update'] > 3.0:
                row['voltage'].setText('STALE')
                row['current'].setText('STALE')
                row['power'].setText('STALE')
                row['error'].setText('OFFLINE')
                row['error'].setStyleSheet('color: gray;')

    def _on_state_combo_changed(self):
        is_custom = self._state_combo.currentData() == -1
        self._custom_val.setVisible(is_custom)

    def get_command_value(self):
        val = self._state_combo.currentData()
        if val == -1:
            return self._custom_val.value()
        return val

    def _do_send(self):
        try:
            # Construct the message (uses default ID 1070)
            msg = dronecan.uavcan.equipment.hardpoint.Command()
            msg.hardpoint_id = self._hardpoint_id.value()
            msg.command = self.get_command_value()

            # Broadcast
            self._node.broadcast(msg)

            # Display
            yaml_str = f"# Message ID: {dronecan.uavcan.equipment.hardpoint.Command.default_dtid}\n" + dronecan.to_yaml(msg)
            self._msg_viewer.setPlainText(yaml_str)
        except Exception as ex:
            self._msg_viewer.setPlainText(f'Sending failed:\n{ex}')

    def __del__(self):
        global _singleton
        _singleton = None
        for h in self._handlers:
            try:
                h.remove()
            except Exception:
                pass

    def closeEvent(self, event):
        global _singleton
        _singleton = None
        for h in self._handlers:
            try:
                h.remove()
            except Exception:
                pass
        super(HardpointsAndCircuitStatusPanel, self).closeEvent(event)


def spawn(parent, node):
    global _singleton
    if _singleton is None:
        _singleton = HardpointsAndCircuitStatusPanel(parent, node)

    _singleton.show()
    _singleton.raise_()
    _singleton.activateWindow()

    return _singleton


get_icon = partial(get_icon, 'fa6s.toggle-on')
