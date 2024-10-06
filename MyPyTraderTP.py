import sys
import json
import requests
import os
import math 
from datetime import datetime, timezone, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, 
                             QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QSpinBox, QSizePolicy,QDoubleSpinBox,
                             QCheckBox, QTableWidget, QTableWidgetItem, QScrollArea, QMenuBar, QAction, QHeaderView, QAbstractItemView)
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon, QPixmap
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer, QThread, pyqtSignal, QMetaObject, pyqtSlot
import databento as db
import pandas as pd 
import time
import sip

class SettingsDialog(QDialog):
    def __init__(self, parent, api_url, databento_key):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        
        layout = QFormLayout(self)
        
        self.url_input = QLineEdit(api_url)
        layout.addRow("Webhook URL:", self.url_input)
        
        self.databento_key_input = QLineEdit(databento_key)
        layout.addRow("Databento API Key:", self.databento_key_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_settings(self):
        return self.url_input.text(), self.databento_key_input.text()

class AddTradeDialog(QDialog):
    def __init__(self, parent=None, current_price=0, current_entry_price=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Update Trade")
        layout = QFormLayout(self)
        
        self.entry_price_input = QLineEdit(str(current_entry_price or current_price))
        layout.addRow("Entry Price:", self.entry_price_input)
        
        self.action_combo = QComboBox()
        self.action_combo.addItems(["buy", "sell"])
        layout.addRow("Action:", self.action_combo)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_trade_info(self):
        return float(self.entry_price_input.text()), self.action_combo.currentText()

class DatabentoWorker(QThread):
    data_received = pyqtSignal(str, object)
    symbol_mapped = pyqtSignal(str, object)

    def __init__(self, key):
        super().__init__()
        self.key = key
        self.subscriptions = {}
        self.is_running = True
        self.client = None

    def add_subscription(self, subscription_id, dataset, schema, symbols, stype_in=None):
        self.subscriptions[subscription_id] = {
            'dataset': dataset,
            'schema': schema,
            'symbols': symbols,
            'stype_in': stype_in
        }

    def run(self):
        try:
            self.client = db.Live(key=self.key)
            for sub_id, sub_info in self.subscriptions.items():
                print(f"Subscribing to {sub_id}: {sub_info}")
                subscribe_params = {
                    'dataset': sub_info['dataset'],
                    'schema': sub_info['schema'],
                    'symbols': sub_info['symbols']
                }
                if sub_info['stype_in']:
                    subscribe_params['stype_in'] = sub_info['stype_in']
                
                self.client.subscribe(**subscribe_params)
            
            for message in self.client:
                if not self.is_running:
                    break
                if isinstance(message, db.SymbolMappingMsg):
                    print(f"Received SymbolMappingMsg: {message}")
                    relevant_sub_id = self.determine_relevant_subscription(message)
                    if relevant_sub_id:
                        print(f"Emitting symbol_mapped for subscription: {relevant_sub_id}")
                        self.symbol_mapped.emit(relevant_sub_id, message)
                    else:
                        print(f"Could not determine relevant subscription for message: {message}")
                else:
                    for sub_id in self.subscriptions:
                        self.data_received.emit(sub_id, message)
        except Exception as e:
            print(f"Error in Databento streaming: {str(e)}")
        finally:
            if self.client:
                self.client.stop()

    def determine_relevant_subscription(self, message):
        for sub_id, sub_info in self.subscriptions.items():
            if message.stype_in_symbol in sub_info['symbols'] or message.stype_out_symbol in sub_info['symbols']:
                return sub_id
        return None

    def stop(self):
        self.is_running = False
        if self.client:
            self.client.stop()



class TPTableWidget(QTableWidget):
    tp_changed = pyqtSignal(int, int, object)

    def __init__(self, trading_app, parent=None):
        super().__init__(parent)
        self.trading_app = trading_app
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Enabled", "Quantity", "Target", "Price", "Status"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.cellChanged.connect(self.on_cell_changed)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalHeader().setDefaultSectionSize(20)  # Set default row height
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.trading_app.adjust_table_size()

    def on_cell_changed(self, row, column):
        if column in [1, 2]:  # Quantity or Target column
            try:
                new_value = float(self.item(row, column).text())
                if column == 1:  # Quantity
                    new_value = int(new_value)
                self.tp_changed.emit(row, column, new_value)
            except ValueError:
                pass  # Ignore invalid input

    def sizeHint(self):
        width = self.horizontalHeader().length() + self.verticalHeader().width() + 20  # Add some padding
        height = self.verticalHeader().length() + self.horizontalHeader().height() + 10
        return QSize(width, height)
    
    def style_empty_rows(self):
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item is None or item.text() == "":
                    new_item = QTableWidgetItem("")
                    new_item.setBackground(QColor(240, 240, 240))  # Light gray background
                    self.setItem(row, col, new_item)
    
    


class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Trading App")
        self.setFixedWidth(450)  # Set a fixed width
        self.setMinimumHeight(400)  # Set a minimum


        self.orders_file = 'active_orders.json'
        self.active_orders = {}
        self.tp_levels = {}
        self.entry_price = None
        
        self.databento_worker = None
        self.is_databento_initialized = False
        
        self.symbol_map = {
            "MES": "MES.c.0", 
            "MNQ": "MNQ.c.0",
            "MGC": "MGC.c.0",
        }
        
        self.default_stop_loss_amounts = {
            "MES": 10,
            "MNQ": 30,
            "MGC": 4
        }



        self.ticker_map = {
            "MNQ": "MNQ1!",
            "MGC": "MGC1!",
            "MES": "MES1!"
        }
        
        self.instrument_id_map = {}
        self.current_prices = {ticker: 0 for ticker in self.symbol_map}
        
        self.load_settings()
        self.load_active_orders()  # Load active orders before setting up UI
        
        self.setup_ui()
        # Connect the new signal
        self.tp_table.tp_changed.connect(self.update_tp_level)
        self.initialize_price_and_stoploss()
        self.update_trade_status()
        self.setup_menu_bar()

        self.update_checkbox.setChecked(True)
        #self.always_on_top_checkbox.setChecked(True)
        
        if self.update_checkbox.isChecked():
            self.initialize_databento_worker()
        
        self.update_ui_from_loaded_data()
        self.check_and_execute_tps_on_startup()

        # Add these lines at the end of __init__
        self.update_tp_table()
        self.update_layout()

         # Add this line at the end of __init__
        QTimer.singleShot(0, self.initial_resize)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
        
        input_layout = QGridLayout()
        input_layout.addWidget(QLabel("Ticker:"), 0, 0)
        self.ticker_combo = QComboBox()
        self.ticker_combo.addItems(self.symbol_map.keys())
        self.ticker_combo.currentTextChanged.connect(self.on_ticker_changed)
        input_layout.addWidget(self.ticker_combo, 0, 1)
        
        input_layout.addWidget(QLabel("Price:"), 1, 0)
        self.price_input = QLineEdit("0")
        self.price_input.setReadOnly(True)
        input_layout.addWidget(self.price_input, 1, 1)
        
        input_layout.addWidget(QLabel("Quantity:"), 2, 0)
        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setValue(5)
        input_layout.addWidget(self.quantity_input, 2, 1)
        
        main_layout.addLayout(input_layout)
        
        databento_layout = QHBoxLayout()
        self.update_checkbox = QCheckBox("Enable price updates")
        self.update_checkbox.stateChanged.connect(self.toggle_price_updates)
        databento_layout.addWidget(self.update_checkbox)
        
        main_layout.addLayout(databento_layout)
        
        stop_loss_layout = QGridLayout()
        stop_loss_layout.addWidget(QLabel("Stop Loss:"), 0, 0)
        self.stop_loss_input = QLineEdit("0")
        stop_loss_layout.addWidget(self.stop_loss_input, 0, 1)
        
        stop_loss_layout.addWidget(QLabel("StopLoss Type:"), 1, 0)
        self.stop_loss_type_combo = QComboBox()
        self.stop_loss_type_combo.addItems(["Market", "Limit", "Trailing"])
        self.stop_loss_type_combo.setCurrentText("Trailing")
        stop_loss_layout.addWidget(self.stop_loss_type_combo, 1, 1)
        
        main_layout.addLayout(stop_loss_layout)
        
        button_layout = QGridLayout()
        self.buy_button = QPushButton("BUY")
        self.buy_button.setStyleSheet("background-color: #007bff; color: black;")
        self.buy_button.clicked.connect(lambda: self.send_order("buy"))
        button_layout.addWidget(self.buy_button, 0, 0)
        
        self.sell_button = QPushButton("SELL")
        self.sell_button.setStyleSheet("background-color: #dc3545; color: black;")
        self.sell_button.clicked.connect(lambda: self.send_order("sell"))
        button_layout.addWidget(self.sell_button, 0, 1)
        
        self.exit_button = QPushButton("EXIT")
        self.exit_button.setStyleSheet("background-color: #ffc107; color: black;")
        self.exit_button.clicked.connect(lambda: self.send_order("exit"))
        button_layout.addWidget(self.exit_button, 1, 0, 1, 2)
        
        main_layout.addLayout(button_layout)
        
        for i in range(input_layout.rowCount()):
            input_layout.itemAtPosition(i, 0).widget().setFixedWidth(80)
        for i in range(stop_loss_layout.rowCount()):
            stop_loss_layout.itemAtPosition(i, 0).widget().setFixedWidth(80)
   
        # Add Trade Management Buttons
        trade_management_layout = QHBoxLayout()
        self.clear_trade_button = QPushButton("Clear Trade")
        self.clear_trade_button.clicked.connect(self.clear_trade)
        trade_management_layout.addWidget(self.clear_trade_button)
        
        self.add_trade_button = QPushButton("Add/Update Trade")
        self.add_trade_button.clicked.connect(self.add_or_update_trade)
        trade_management_layout.addWidget(self.add_trade_button)
        
        main_layout.addLayout(trade_management_layout)

        # TP Table
        self.tp_table = TPTableWidget(self)
        self.tp_table_container = QWidget()
        self.tp_table_container.setLayout(QVBoxLayout())
        self.tp_table_container.layout().setContentsMargins(0, 0, 0, 0)
        self.tp_table_container.layout().addWidget(self.tp_table)
        self.tp_table_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        main_layout.addWidget(self.tp_table_container)

        # Add buttons for TP management
        tp_button_layout = QHBoxLayout()
        self.add_tp_button = QPushButton("Add TP")
        self.add_tp_button.clicked.connect(self.add_tp_level)
        self.remove_tp_button = QPushButton("Remove TP")
        self.remove_tp_button.clicked.connect(self.remove_tp_level)
        tp_button_layout.addWidget(self.add_tp_button)
        tp_button_layout.addWidget(self.remove_tp_button)
        main_layout.addLayout(tp_button_layout)
        
        # Trade status label
        status_layout = QHBoxLayout()
        self.trade_status_label = QLabel("Status: Not in trade")
        status_layout.addWidget(self.trade_status_label)
        status_layout.addStretch()
        
        main_layout.addLayout(status_layout)

        # Response area
        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        main_layout.addWidget(self.response_area)

        # Set size policy for the central widget to be expanding
        central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def initial_resize(self):
        self.update_tp_table()
    

    def on_checkbox_changed(self, row, state):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.tp_levels and row < len(self.tp_levels[current_ticker]):
            self.tp_levels[current_ticker][row]['enabled'] = state == Qt.Checked
            self.save_active_orders()
            print(f"TP level {row} for {current_ticker} {'enabled' if state == Qt.Checked else 'disabled'}")


    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.adjust_table_size)

    def setup_menu_bar(self):
        menu_bar = self.menuBar()

        # Create a "View" menu
        preference_menu = menu_bar.addMenu("Preference")

        # Add 'Always on Top' action
        self.always_on_top_action = QAction("Always on Top", self, checkable=True)
        self.always_on_top_action.triggered.connect(self.toggle_always_on_top)
        preference_menu.addAction(self.always_on_top_action)

        # Add 'Open Settings' action
        open_settings_action = QAction("Open Settings", self)
        open_settings_action.triggered.connect(self.open_settings)
        preference_menu.addAction(open_settings_action)

        # If on macOS, set the menu bar to native
        if sys.platform == "darwin":
            menu_bar.setNativeMenuBar(True)
        else:
            # For non-macOS platforms, you might want to keep the menu within the window
            menu_bar.setNativeMenuBar(False)

    def update_layout(self):
        # Force the central widget to update its layout
        self.centralWidget().updateGeometry()
        self.centralWidget().layout().update()
        
        # Update the main window layout
        self.updateGeometry()
        self.update()

    def toggle_always_on_top(self, checked):
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            self.update_response_area("Window set to always on top.\n")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()
            self.update_response_area("Window no longer always on top.\n")

    def open_settings(self):
        dialog = SettingsDialog(self, self.api_url, self.databento_key)
        if dialog.exec_() == QDialog.Accepted:
            self.api_url, self.databento_key = dialog.get_settings()
            self.save_settings()
            self.update_response_area(f"Settings updated:\nWebhook URL: {self.api_url}\nDatabento API Key: {'*' * len(self.databento_key)}\n")
            self.initialize_databento_client()

    def save_active_orders(self):
        data_to_save = {
            'active_orders': self.active_orders,
            'tp_levels': self.tp_levels
        }
        with open(self.orders_file, 'w') as f:
            json.dump(data_to_save, f, indent=2)



    def load_active_orders(self):
        if os.path.exists(self.orders_file):
            try:
                with open(self.orders_file, 'r') as f:
                    data = json.load(f)
                    self.active_orders = data.get('active_orders', {})
                    self.tp_levels = data.get('tp_levels', {})
                
                # Validate loaded data
                for ticker, order in list(self.active_orders.items()):
                    if not isinstance(order, dict) or 'entry_price' not in order or 'action' not in order:
                        del self.active_orders[ticker]
                        print(f"Removed invalid order for {ticker}")
                
                for ticker, tps in list(self.tp_levels.items()):
                    if not isinstance(tps, list):
                        del self.tp_levels[ticker]
                        print(f"Removed invalid TP levels for {ticker}")
                    else:
                        self.tp_levels[ticker] = [tp for tp in tps if isinstance(tp, dict) and 'target' in tp and 'quantity' in tp]
                
                print(f"Loaded active orders: {self.active_orders}")
                print(f"Loaded TP levels: {self.tp_levels}")
            except json.JSONDecodeError:
                print(f"Error loading {self.orders_file}. Starting with empty orders and TP levels.")
                self.active_orders = {}
                self.tp_levels = {}
        else:
            self.active_orders = {}
            self.tp_levels = {} 

    def update_ui_from_loaded_data(self):
        current_ticker = self.ticker_combo.currentText()
        
        # Update trade status
        self.update_trade_status()
        
        # Update TP table
        self.update_tp_table()
        
        # If in a trade, update entry price and other relevant fields
        if current_ticker in self.active_orders:
            order = self.active_orders[current_ticker]
            self.entry_price = order['entry_price']
            self.price_input.setText(f"{self.entry_price:.2f}")
        else:
            # If not in a trade, use the current price
            current_price = self.current_prices.get(current_ticker, 0)
            self.price_input.setText(f"{current_price:.2f}")
        
        print(f"Updated UI for ticker: {current_ticker}")
        print(f"Active order: {self.active_orders.get(current_ticker)}")
        print(f"TP levels: {self.tp_levels.get(current_ticker)}")

    def update_trade_status(self):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.active_orders:
            order = self.active_orders[current_ticker]
            entry_price = order['entry_price']
            position_type = "Long" if order['action'] == 'buy' else "Short"
            status_text = f"Status: In trade @ {entry_price:.2f} ({position_type})"
            self.trade_status_label.setText(status_text)
            self.trade_status_label.setStyleSheet("color: green;")
        else:
            self.trade_status_label.setText("Status: Not in trade")
            self.trade_status_label.setStyleSheet("color: red;")
        
        print(f"Updated trade status for {current_ticker}: {'In trade' if current_ticker in self.active_orders else 'Not in trade'}")

    

    def update_tp_level(self, row, column, new_value):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.tp_levels and row < len(self.tp_levels[current_ticker]):
            if column == 1:  # Quantity
                self.tp_levels[current_ticker][row]['quantity'] = new_value
            elif column == 2:  # Target
                self.tp_levels[current_ticker][row]['target'] = new_value
            self.save_active_orders()
            self.update_tp_table()  # Refresh the table display
        print(f"Updated TP level: Ticker={current_ticker}, Row={row}, Column={column}, New Value={new_value}")



    # def update_tp_table(self):
    #     self.tp_table.blockSignals(True)
        
    #     current_ticker = self.ticker_combo.currentText()
    #     current_price = float(self.price_input.text())
        
    #     if current_ticker in self.tp_levels:
    #         tp_levels = self.tp_levels[current_ticker]
    #         self.tp_table.setRowCount(len(tp_levels))
            
    #         in_trade = current_ticker in self.active_orders
    #         entry_price = self.active_orders[current_ticker]['entry_price'] if in_trade else None
    #         action = self.active_orders[current_ticker]['action'] if in_trade else None
            
    #         for row, tp in enumerate(tp_levels):
    #                            # Enable/Disable checkbox
    #             checkbox = QCheckBox()
    #             checkbox.setChecked(tp.get('enabled', True))
    #             checkbox.stateChanged.connect(lambda state, r=row: self.on_checkbox_changed(r, state))
    #             self.tp_table.setCellWidget(row, 0, checkbox)
                
    #             # Quantity
    #             self.tp_table.setItem(row, 1, QTableWidgetItem(str(tp['quantity'])))
                
    #             # Target
    #             self.tp_table.setItem(row, 2, QTableWidgetItem(str(tp['target'])))
                
    #             # Price
    #             if in_trade:
    #                 tp_price = entry_price + tp['target'] if action == 'buy' else entry_price - tp['target']
    #             else:
    #                 tp_price = current_price + tp['target']
    #             self.tp_table.setItem(row, 3, QTableWidgetItem(f"{tp_price:.2f}"))
                
    #             # Status
    #             status = "Hit" if tp.get('hit', False) else "Active"
    #             self.tp_table.setItem(row, 4, QTableWidgetItem(status))
                
    #             if tp.get('hit', False):
    #                 for col in range(5):
    #                     item = self.tp_table.item(row, col)
    #                     if item:
    #                         item.setBackground(QColor(200, 255, 200))
    #             # (Populate table rows as before)
    #             pass
    #     else:
    #         self.tp_table.setRowCount(0)

            
    #     self.tp_table.blockSignals(False)


    #     self.tp_table.style_empty_rows()
    #     self.adjust_table_size()
        
    #     print(f"Updated TP table for {current_ticker} with {len(self.tp_levels.get(current_ticker, []))} levels")



    def update_tp_table(self):
        self.tp_table.blockSignals(True)
        
        current_ticker = self.ticker_combo.currentText()
        current_price = float(self.price_input.text())
        
        if current_ticker in self.tp_levels and self.tp_levels[current_ticker]:
            tp_levels = self.tp_levels[current_ticker]
            self.tp_table.setRowCount(len(tp_levels))
            in_trade = current_ticker in self.active_orders
            entry_price = self.active_orders[current_ticker]['entry_price'] if in_trade else None
            action = self.active_orders[current_ticker]['action'] if in_trade else None
            
            for row, tp in enumerate(tp_levels):
                               # Enable/Disable checkbox
                checkbox = QCheckBox()
                checkbox.setChecked(tp.get('enabled', True))
                checkbox.stateChanged.connect(lambda state, r=row: self.on_checkbox_changed(r, state))
                self.tp_table.setCellWidget(row, 0, checkbox)
                
                # Quantity
                self.tp_table.setItem(row, 1, QTableWidgetItem(str(tp['quantity'])))
                
                # Target
                self.tp_table.setItem(row, 2, QTableWidgetItem(str(tp['target'])))
                
                # Price
                if in_trade:
                    tp_price = entry_price + tp['target'] if action == 'buy' else entry_price - tp['target']
                else:
                    tp_price = current_price + tp['target']
                self.tp_table.setItem(row, 3, QTableWidgetItem(f"{tp_price:.2f}"))
                
                # Status
                status = "Hit" if tp.get('hit', False) else "Active"
                self.tp_table.setItem(row, 4, QTableWidgetItem(status))
                
                if tp.get('hit', False):
                    for col in range(5):
                        item = self.tp_table.item(row, col)
                        if item:
                            item.setBackground(QColor(200, 255, 200))
                # (Populate table rows as before)
                pass

        else:
            # Add empty rows if there's no data
            empty_row_count = 0  # You can adjust this number as needed
            self.tp_table.setRowCount(empty_row_count)
            
            # for row in range(empty_row_count):
            #     for col in range(5):  # 5 is the number of columns in your table
            #         # if col == 0:
            #         #     self.tp_table.setItem(row, col, QTableWidgetItem(""))
            #         #     # checkbox = QCheckBox()
            #         #     # checkbox.setEnabled(False)
            #         #     # self.tp_table.setCellWidget(row, col, checkbox)
            #         # else:
            #             self.tp_table.setItem(row, col, QTableWidgetItem(""))

        self.tp_table.blockSignals(False)
        
        # Adjust table size
        self.adjust_table_size()
        #self.tp_table.style_empty_rows()
        
        print(f"Updated TP table for {current_ticker} with {len(self.tp_levels.get(current_ticker, []))} levels")

    def add_tp_level(self):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker not in self.tp_levels:
            self.tp_levels[current_ticker] = []
        
        current_price = float(self.price_input.text())
        
        # Create a dialog to get TP details from the user
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Take Profit Level")
        layout = QFormLayout(dialog)
        
        quantity_input = QSpinBox()
        quantity_input.setMinimum(1)
        quantity_input.setValue(1)
        layout.addRow("Quantity:", quantity_input)
        
        target_input = QDoubleSpinBox()
        target_input.setMinimum(0.01)
        target_input.setMaximum(1000000)
        target_input.setValue(10)
        target_input.setDecimals(2)
        layout.addRow("Target (offset from entry):", target_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec_() == QDialog.Accepted:
            target = target_input.value()
            if current_ticker in self.active_orders:
                entry_price = self.active_orders[current_ticker]['entry_price']
                action = self.active_orders[current_ticker]['action']
                calculated_price = entry_price + target if action == 'buy' else entry_price - target
            else:
                calculated_price = current_price + target

            new_tp = {
                'enabled': True,
                'quantity': quantity_input.value(),
                'target': target,
                'price': calculated_price,
                'hit': False
            }
            self.tp_levels[current_ticker].append(new_tp)

            self.update_tp_table()
            self.save_active_orders()
            self.adjust_table_size()
 
    def update_tp_enabled(self, row, enabled):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.tp_levels and row < len(self.tp_levels[current_ticker]):
            self.tp_levels[current_ticker][row]['enabled'] = enabled
            self.save_active_orders()
            print(f"Updated TP enabled status: Ticker={current_ticker}, Row={row}, Enabled={enabled}")

    def on_ticker_changed(self, ticker):
        price = self.current_prices.get(ticker, 0)
        self.price_input.setText(f"{price:.2f}")
        self.update_default_values(ticker)
        if self.is_databento_initialized:
            self.initialize_databento_worker()
        self.update_trade_status()
        self.update_tp_table()
        print(f"Ticker changed to {ticker}")


    def clear_trade(self):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.active_orders:
            del self.active_orders[current_ticker]
        if current_ticker in self.tp_levels:
            del self.tp_levels[current_ticker]
        self.entry_price = None
        self.update_trade_status()
        self.save_active_orders()
        self.update_tp_table()
        self.update_response_area("Trade cleared. All TPs removed.\n")


    def add_or_update_trade(self):
        current_price = float(self.price_input.text())
        current_ticker = self.ticker_combo.currentText()
        current_entry_price = self.active_orders.get(current_ticker, {}).get('entry_price')
        dialog = AddTradeDialog(self, current_price, current_entry_price)
        
        if dialog.exec_():
            entry_price, action = dialog.get_trade_info()
            
            self.active_orders[current_ticker] = {
                "symbol": current_ticker,
                "action": action,
                "quantity": self.quantity_input.value(),
                "entry_price": entry_price,
                "timestamp": int(time.time())
            }
            
            if current_ticker not in self.tp_levels:
                self.tp_levels[current_ticker] = []
            
            
            self.save_active_orders()
            self.update_trade_status()
            self.update_tp_table()
            self.update_response_area(f"Trade {'updated' if current_entry_price else 'added'}. Entry price: {entry_price}, Action: {action}\n")
            
            # Force layout update
            QTimer.singleShot(0, self.adjust_table_size)
            
            # Check and potentially execute TPs immediately
            self.check_and_update_tp_levels(current_ticker, current_price)


    def force_layout_update(self):
        # Force the layout to update
        self.tp_table_container.updateGeometry()
        self.centralWidget().updateGeometry()
        
        # Use a QTimer to defer the final adjustment
        QTimer.singleShot(0, self.final_layout_adjustment)

    def final_layout_adjustment(self):
        # Adjust the table height
        self.adjust_table_height()
        
        # Force the main window to adjust its size if needed

    def adjust_table_height(self):
        if self.is_adjusting:
            return
        
        self.is_adjusting = True
        
        row_count = self.tp_table.rowCount()
        header_height = self.tp_table.horizontalHeader().height()
        row_height = self.tp_table.verticalHeader().defaultSectionSize()
        total_height = header_height + (row_count * row_height)
        max_height = 300  # Maximum height before scrolling
        new_height = min(total_height + 2, max_height)  # +2 for borders
        
        self.tp_table_container.setFixedHeight(new_height)
        
        # Ensure the table width matches the container width
        self.tp_table.setFixedWidth(self.tp_table_container.width())
        
        self.is_adjusting = False


    def adjust_table_size(self):
        # Adjust width to match container width
        available_width = self.tp_table_container.width()
        self.tp_table.setFixedWidth(available_width)
        
        # Adjust height
        if self.tp_table.rowCount() < 5:
            row_count = 5
        else:
            row_count = self.tp_table.rowCount()

        header_height = self.tp_table.horizontalHeader().height()
        row_height = self.tp_table.verticalHeader().defaultSectionSize()
        total_height = header_height + (row_count * row_height)
        
        # Set the table height to fit all rows without scrolling
        self.tp_table_container.setFixedHeight(total_height)
        
        # Resize columns to fit content
        self.tp_table.resizeColumnsToContents()
        
        # Stretch columns to fill available width
        header = self.tp_table.horizontalHeader()
        for i in range(self.tp_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
        
        # Force immediate update
        self.tp_table.updateGeometry()
        self.tp_table_container.updateGeometry()

    def check_and_execute_tps_on_startup(self):
        for ticker, order in self.active_orders.items():
            current_price = self.current_prices.get(ticker, order['entry_price'])
            self.check_and_update_tp_levels(ticker, current_price)

    def check_and_update_tp_levels(self, ticker, current_price):
        if ticker not in self.active_orders or ticker not in self.tp_levels:
            return

        for tp in self.tp_levels[ticker]:
            if tp['enabled'] and not tp['hit']:
                if (self.active_orders[ticker]['action'] == 'buy' and current_price >= tp['price']) or \
                (self.active_orders[ticker]['action'] == 'sell' and current_price <= tp['price']):
                    tp['hit'] = True
                    self.execute_tp_order(ticker, tp)
        
        self.update_tp_table()


    def execute_tp_order(self, ticker, tp):
        self.update_response_area(f"TP hit for {ticker}: {tp['quantity']} @ {tp['price']:.2f}\n")
        
        # Update the active order
        if ticker in self.active_orders:
            self.active_orders[ticker]['quantity'] -= tp['quantity']
            if self.active_orders[ticker]['quantity'] <= 0:
                del self.active_orders[ticker]
                self.update_response_area(f"Order for {ticker} fully closed and removed from active orders.\n")
        
        self.save_active_orders()
        self.update_trade_status()

    def remove_tp_level(self):
        current_ticker = self.ticker_combo.currentText()
        selected_rows = self.tp_table.selectionModel().selectedRows()
        
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select a TP level to remove.")
            return
        
        row = selected_rows[0].row()
        
        if current_ticker in self.tp_levels and row < len(self.tp_levels[current_ticker]):
            removed_tp = self.tp_levels[current_ticker].pop(row)
            self.update_tp_table()
            self.save_active_orders()
            self.adjust_table_size()
            print(f"Removed TP level: {removed_tp}")
        else:
            print("Invalid row selected for removal")

    def check_and_update_tp_levels(self, ticker, current_price):
        if ticker not in self.tp_levels:
            return

        if ticker in self.active_orders:
            order = self.active_orders[ticker]
            action = order['action']
            entry_price = order['entry_price']

            for tp in self.tp_levels[ticker]:
                if tp['enabled'] and not tp['hit']:
                    tp_price = entry_price + tp['target'] if action == 'buy' else entry_price - tp['target']
                    if (action == 'buy' and current_price >= tp_price) or \
                       (action == 'sell' and current_price <= tp_price):
                        tp['hit'] = True
                        self.execute_tp_order(ticker, tp)
        
        self.update_tp_table()


    def handle_databento_data(self, subscription_id, message):
        if subscription_id == "main":
            try:
                if hasattr(message, 'instrument_id'):
                    instrument_id = message.instrument_id
                    symbol = self.instrument_id_map.get(instrument_id)
                    
                    scale_factor = 1000000000  # 1 billion

                    if symbol:
                        ticker = next((key for key, value in self.symbol_map.items() if value == symbol), None)
                        
                        if ticker and hasattr(message, 'close'):
                            close_price = message.close / scale_factor
                            
                            self.current_prices[ticker] = close_price

                            if ticker == self.ticker_combo.currentText():
                                self.price_input.setText(f"{close_price:.2f}")
                                self.update_tp_table()
                                self.check_and_update_tp_levels(ticker, close_price)
            except Exception as e:
                print(f"Error processing data: {type(e).__name__}: {str(e)}")


    def load_settings(self):
        if os.path.exists('settings.json'):
            try:
                with open('settings.json', 'r') as f:
                    settings = json.load(f)
                    self.api_url = settings.get('api_url', "https://your-api-endpoint.com/orders")
                    self.databento_key = settings.get('databento_key', "")
            except json.JSONDecodeError:
                self.use_default_settings()
        else:
            self.use_default_settings()

    def use_default_settings(self):
        self.api_url = "https://your-api-endpoint.com/orders"
        self.databento_key = ""

    def save_settings(self):
        settings = {
            'api_url': self.api_url,
            'databento_key': self.databento_key
        }
        with open('settings.json', 'w') as f:
            json.dump(settings, f, indent=2)

    def initialize_price_and_stoploss(self):
        initial_ticker = self.ticker_combo.currentText()
        self.update_default_values(initial_ticker)

    def update_default_values(self, ticker):
        default_stop_loss = self.default_stop_loss_amounts.get(ticker, 0)
        self.stop_loss_input.setText(str(default_stop_loss))

    def get_stop_loss_type(self, gui_type):
        if gui_type == "Market":
            return "stop"
        elif gui_type == "Limit":
            return "stop_limit"
        elif gui_type == "Trailing":
            return "trailing_stop"
        else:
            return "stop"
        
    def send_order(self, action):
        ticker = self.ticker_combo.currentText()
        symbol = self.ticker_map.get(ticker, ticker)

        try:
            current_price = float(self.price_input.text())
            quantity = self.quantity_input.value()
            stop_loss_amount = float(self.stop_loss_input.text())
        except ValueError:
            self.update_response_area("Error: Invalid input for price or stop loss.\n")
            return
        
        order = {
            "ticker": symbol,
            "action": action,
            "orderType": "market",
            "limitPrice": current_price,
            "quantity": quantity
        }
        
        if action in ["buy", "sell"]:
            stop_loss_type = self.stop_loss_type_combo.currentText()
            if stop_loss_type == "Trailing":
                order["stopLoss"] = {
                    "type": "trailing_stop",
                    "trailAmount": stop_loss_amount
                }
            else:
                if action == "buy":
                    stop_loss_price = current_price - stop_loss_amount
                else:  # sell
                    stop_loss_price = current_price + stop_loss_amount
                
                order["stopLoss"] = {
                    "type": self.get_stop_loss_type(stop_loss_type),
                    "stopPrice": stop_loss_price
                }
        
        try:
            response = requests.post(self.api_url, json=order)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get("success"):
                if action != "exit":
                    self.active_orders[ticker] = {
                        "symbol": symbol,
                        "action": action,
                        "quantity": quantity,
                        "entry_price": current_price,
                        "timestamp": int(time.time())
                    }
                    self.save_active_orders()
                
                response_text = f"{action.capitalize()} order sent successfully for {symbol}!\n"
                if action != "exit":
                    response_text += f"Entry Price: {current_price}\n"
                if "stopLoss" in order:
                    response_text += f"Stop Loss: {order['stopLoss']['type']} @ {order['stopLoss'].get('stopPrice', order['stopLoss'].get('trailAmount')):.2f}\n"
                
                if action == "exit":
                    if ticker in self.active_orders:
                        del self.active_orders[ticker]
                        self.save_active_orders()
                        response_text += f"Removed order for {ticker} from active orders.\n"
                
                self.update_trade_status()
                self.update_tp_table()
            else:
                response_text = f"Error sending {action} order for {symbol}: Unsuccessful response from server\n"
                response_text += f"Response: {json.dumps(response_data, indent=2)}\n\n"
            
            self.update_response_area(response_text)
        except requests.RequestException as e:
            error_text = f"Error sending {action} order for {symbol}: {str(e)}\n\n"
            self.update_response_area(error_text)

    def update_response_area(self, text):
        self.response_area.append(text)
        self.response_area.verticalScrollBar().setValue(
            self.response_area.verticalScrollBar().maximum()
        )

    def initialize_databento_worker(self):
        if self.databento_worker:
            self.stop_databento_worker()

        try:
            current_ticker = self.ticker_combo.currentText()
            symbol = self.symbol_map.get(current_ticker)
            
            if not symbol:
                raise ValueError(f"No symbol mapping found for ticker: {current_ticker}")

            self.databento_worker = DatabentoWorker(key=self.databento_key)
            self.databento_worker.add_subscription(
                subscription_id="main",
                dataset="GLBX.MDP3",
                schema="ohlcv-1s",
                stype_in="continuous",
                symbols=[symbol]
            )
            
            self.databento_worker.data_received.connect(self.handle_databento_data)
            self.databento_worker.symbol_mapped.connect(self.handle_symbol_mapping)
            self.databento_worker.start()
            
            self.is_databento_initialized = True
            self.update_response_area(f"Databento worker initialized for {current_ticker}. Starting to receive price updates.\n")
        except Exception as e:
            self.update_response_area(f"Error initializing Databento worker: {str(e)}\n")
            self.databento_worker = None
            self.is_databento_initialized = False



    def handle_symbol_mapping(self, subscription_id, message):
        if subscription_id == "main":
            instrument_id = message.instrument_id
            continuous_symbol = message.stype_in_symbol
            raw_symbol = message.stype_out_symbol
            self.instrument_id_map[instrument_id] = continuous_symbol
            print(f"Symbol Mapping: {continuous_symbol} ({raw_symbol}) has an instrument ID of {instrument_id}")


    def toggle_price_updates(self, state):
        if state == Qt.Checked:
            self.update_response_area("Initializing Databento connection...\n")
            self.initialize_databento_worker()
        else:
            self.update_response_area("Stopping Databento connection...\n")
            self.stop_databento_worker()

    def stop_databento_worker(self):
        if self.databento_worker:
            self.databento_worker.stop()
            self.databento_worker.wait()
            self.databento_worker = None
        self.is_databento_initialized = False
        self.update_response_area("Databento connection stopped. Price updates disabled.\n")

    def closeEvent(self, event):
        self.save_active_orders()
        self.stop_databento_worker()
        event.accept()

    def update_all_tp_amounts(self):
        current_ticker = self.ticker_combo.currentText()
        current_price = float(self.price_input.text())
        if current_ticker in self.tp_levels:
            for tp in self.tp_levels[current_ticker]:
                if not tp['hit']:
                    if current_ticker in self.active_orders:
                        action = self.active_orders[current_ticker]['action']
                        entry_price = self.active_orders[current_ticker]['entry_price']
                        if action == 'buy':
                            tp['price'] = entry_price + tp['target']
                        else:
                            tp['price'] = entry_price - tp['target']
            self.update_tp_table()

    def monitor_tp_levels(self, ticker):
        if ticker not in self.active_orders:
            return

        order = self.active_orders[ticker]
        current_price = self.current_prices.get(ticker, order['entry_price'])
        self.check_and_update_tp_levels(ticker, current_price)

 

    def execute_tp_order(self, ticker, tp):
        self.update_response_area(f"TP hit for {ticker}: {tp['quantity']} @ {tp['price']:.2f}\n")
        
        if ticker in self.active_orders:
            self.active_orders[ticker]['quantity'] -= tp['quantity']
            if self.active_orders[ticker]['quantity'] <= 0:
                del self.active_orders[ticker]
                self.update_response_area(f"Order for {ticker} fully closed and removed from active orders.\n")
        
        self.save_active_orders()
        self.update_trade_status()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TradingApp()
    ex.show()
    sys.exit(app.exec_())