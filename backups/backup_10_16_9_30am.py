import sys
import json
import requests
import os
import math 
from datetime import datetime, timezone, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, 
                             QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QSpinBox, QSizePolicy,QDoubleSpinBox,
                             QCheckBox, QTableWidget, QTableWidgetItem, QScrollArea, QMenuBar, QAction, QHeaderView, QAbstractItemView, QDateTimeEdit)
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon, QPixmap, QPalette
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer, QThread, pyqtSignal, QMetaObject, pyqtSlot, QDateTime
import databento as db
import pandas as pd 
import time
import sip
from pytz import UTC
import re

class ArchiveWorker(QThread):
    error_signal = pyqtSignal(str)

    def __init__(self, archive_key):
        super().__init__()
        self.archive_key = archive_key
        self.running = True
        self.live = None

    def get_latest_timestamp(self, file_path):
        try:
            dbn_store = db.read_dbn(file_path)
            df = dbn_store.to_df(schema="ohlcv-1m")
            if not df.empty:
                return df.index[-1]
        except Exception as e:
            print(f"Error reading DBN file: {e}")
        return None

    def create_or_continue_file(self, file_path, start_time):
        is_new_file = not os.path.exists(file_path)
        print(f"{'Creating new' if is_new_file else 'Continuing'} file {file_path}")
        
        self.live = db.Live(key=self.archive_key)
        self.live.subscribe(
            dataset="GLBX.MDP3",
            schema="ohlcv-1m",
            stype_in="continuous",
            symbols=["MES.c.0", "MNQ.c.0", "MCL.c.0", "MGC.c.1, ES.c.0", "NQ.c.0", "CL.c.0", "GC.c.1"],
            start=start_time
        )
        
        if is_new_file:
            self.live.add_stream(file_path)
            print(f"Added new stream for {file_path}")

        previous_timestamp = None
        with open(file_path, 'ab') as file:
            for rec in self.live:  # This will automatically start the streaming
                if not self.running:
                    break
                if rec is not None:
                    file.write(bytes(rec))
                    file.flush()  # Ensure data is written to disk

                    # Periodically check and report progress
                    latest_timestamp = self.get_latest_timestamp(file_path)
                    if latest_timestamp and latest_timestamp != previous_timestamp:
                        previous_timestamp = latest_timestamp
                        print(f"Data written up to {previous_timestamp}")
                else:
                    print("Warning: Received invalid record from live_client")

        if self.live:
            self.live.stop()

    def run(self):
        archive_dir = "databento_archives"
        os.makedirs(archive_dir, exist_ok=True)

        while self.running:
            try:
                current_date = datetime.now().strftime('%Y%m%d')
                filename = f"ohlcv-1m_{current_date}.dbn"
                self.file_path = os.path.join(archive_dir, filename)

                if os.path.exists(self.file_path):
                    # File exists, start from the latest timestamp in the file
                    last_timestamp = self.get_latest_timestamp(self.file_path)
                    start_time = last_timestamp + timedelta(minutes=1) if last_timestamp else datetime.now().replace(second=0, microsecond=0)
                else:
                    # New file, start from 2 hours ago
                    start_time = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=20)

                self.create_or_continue_file(self.file_path, start_time)

                # After processing for the current day, wait until the next day
                tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                sleep_time = (tomorrow - datetime.now()).total_seconds()
                time.sleep(sleep_time)

            except Exception as e:
                self.error_signal.emit(f"Error in archiving: {str(e)}")
                time.sleep(60)  # Wait before retrying

    def stop(self):
        self.running = False
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
        if self.live:
            self.live.stop()

class SettingsDialog(QDialog):
    def __init__(self, parent, api_url, databento_key, archive_key, atr_period, atr_lookback):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        
        layout = QFormLayout(self)
        
        self.url_input = QLineEdit(api_url)
        layout.addRow("Webhook URL:", self.url_input)
        
        self.databento_key_input = QLineEdit(databento_key)
        layout.addRow("Databento API Key:", self.databento_key_input)
        
        self.archive_key_input = QLineEdit(archive_key)
        layout.addRow("Archive Key:", self.archive_key_input)
        
        self.atr_period_input = QSpinBox()
        self.atr_period_input.setRange(1, 100)
        self.atr_period_input.setValue(atr_period)
        layout.addRow("ATR Period:", self.atr_period_input)
        
        self.atr_lookback_input = QSpinBox()
        self.atr_lookback_input.setRange(60, 1440)  # 1 hour to 1 day in minutes
        self.atr_lookback_input.setValue(atr_lookback)
        layout.addRow("ATR Lookback (minutes):", self.atr_lookback_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


    def get_settings(self):
        return (self.url_input.text(), self.databento_key_input.text(), 
                self.archive_key_input.text(), self.atr_period_input.value(), 
                self.atr_lookback_input.value())



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
    connection_error = pyqtSignal(str)

    def __init__(self, key, is_replay=False, replay_start=None, replay_symbol=None):
        super().__init__()
        self.key = key
        self.subscriptions = {}
        self.is_running = True
        self.client = None
        self.is_replay = is_replay
        self.replay_start = replay_start
        self.replay_symbol = replay_symbol
        self.max_retries = 5
        self.retry_delay = 5  # seconds

    def add_subscription(self, subscription_id, dataset, schema, symbols, stype_in=None):
        self.subscriptions[subscription_id] = {
            'dataset': dataset,
            'schema': schema,
            'symbols': symbols,
            'stype_in': stype_in
        }


    def run(self):
        retry_count = 0
        while self.is_running and retry_count < self.max_retries:
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
                    
                    if self.is_replay:
                        subscribe_params['start'] = self.replay_start
                        subscribe_params['symbols'] = self.replay_symbol
                    
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
                
                # If we get here, it means the connection was closed normally
                break
            
            except Exception as e:
                retry_count += 1
                error_msg = f"Error in Databento streaming (attempt {retry_count}/{self.max_retries}): {str(e)}"
                print(error_msg)
                self.connection_error.emit(error_msg)
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    print("Max retries reached. Stopping Databento worker.")
                    break
        
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
        self.is_editing = False

    def on_cell_changed(self, row, column):
        if not self.is_editing and column in [1, 2]:  # Quantity or Target column
            self.is_editing = True
            try:
                new_value = float(self.item(row, column).text())
                if column == 1:  # Quantity
                    new_value = int(new_value)
                self.tp_changed.emit(row, column, new_value)
            except ValueError:
                pass  # Ignore invalid input
            finally:
                self.is_editing = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.trading_app.adjust_table_size()

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
                
        
        self.last_tp_table_update = 0
        self.tp_table_update_interval = 60  # in seconds


        self.orders_file = 'active_orders.json'
        self.active_orders = {}
        self.tp_levels = {}
        self.entry_price = None
        
        self.databento_worker = None
        self.is_databento_initialized = False
        
        self.symbol_map = {
            "MES": "MES.c.0", 
            "MNQ": "MNQ.c.0",
            "MGC": "MGC.c.1",
            "MCL": "MCL.c.0"
        }
        
        self.default_stop_loss_amounts = {
            "MES": 10,
            "MNQ": 30,
            "MGC": 4,
            "MCL": .73
        }



        self.ticker_map = {
            "MNQ": "MNQ1!",
            #"MGC": "MGC1!",
            "MGC": "MGCZ2024",
            "MES": "MES1!",
            "MCL": "MCL1!"
        }
        
        self.instrument_id_map = {}
        self.current_prices = {ticker: 0 for ticker in self.symbol_map}
        self.atr_period = 14  # Default ATR period
        self.atr_lookback = 390  # Default to 6.5 hours (typical trading day)
        self.atr_values = {}  # Dictionary to store ATR values for each ticker
        
        
        self.load_settings()
        self.load_active_orders()  # Load active orders before setting up UI
        
        #Replay mode
        self.is_replay_mode = False

        #self.archive_key = ""
        self.archive_worker = None

        self.trade_timer = None
        self.trade_start_time = None
        self.timer_duration = 5 * 60  # 5 minutes in seconds
        self.timer_expired_message_shown = False
        
        
        self.setup_ui()
        self.update_contract_type()
        # Connect the new signal
        self.tp_table.tp_changed.connect(self.update_tp_level)
        self.initialize_price_and_stoploss()
        self.update_trade_status()
        self.setup_menu_bar()

        # Initialize price updates by default
        self.enable_price_updates_action.setChecked(True)
        self.toggle_price_updates(True)

        if self.archive_key:
            self.enable_archive_action.setChecked(False)
            self.toggle_archive(False)
        else:
            self.enable_archive_action.setChecked(False) 

        # self.update_checkbox.setChecked(True)
        # #self.always_on_top_checkbox.setChecked(True)
        
        self.databento_reconnect_timer = QTimer(self)

        # if self.update_checkbox.isChecked():
        #     self.databento_reconnect_timer.timeout.connect(self.initialize_databento_worker)

            #self.initialize_databento_worker()
        
        self.update_ui_from_loaded_data()
        #self.check_and_execute_tps_on_startup()

   

        # Add these lines at the end of __init__
        self.update_tp_table()
        self.update_layout()
        self.update_atr()
        
        QApplication.instance().aboutToQuit.connect(self.cleanup)
         # Add this line at the end of __init__
        QTimer.singleShot(0, self.initial_resize)
        # Add this at the end of __init__
        QTimer.singleShot(5000, self.delayed_tp_check)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
        
        input_layout = QGridLayout()

        # Add Ticker selection
        input_layout.addWidget(QLabel("Ticker:"), 0, 0)
        self.ticker_combo = QComboBox()
        self.ticker_combo.currentTextChanged.connect(self.on_ticker_changed)
        input_layout.addWidget(self.ticker_combo, 0, 1)

        # Add Contract Type selection
        input_layout.addWidget(QLabel("Contract Type:"), 0, 2)
        self.contract_type_combo = QComboBox()
        self.contract_type_combo.addItems(["Micros", "Minis"])
        self.contract_type_combo.currentIndexChanged.connect(lambda _: self.update_contract_type())
        input_layout.addWidget(self.contract_type_combo, 0, 3)

        # Price input
        input_layout.addWidget(QLabel("Price:"), 1, 0)
        self.price_input = QLineEdit("0")
        self.price_input.setReadOnly(True)
        input_layout.addWidget(self.price_input, 1, 1)

        # Quantity input
        input_layout.addWidget(QLabel("Quantity:"), 2, 0)
        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setValue(5)
        input_layout.addWidget(self.quantity_input, 2, 1)

        main_layout.addLayout(input_layout)

        # Stop Loss layout
        stop_loss_layout = QGridLayout()
        stop_loss_layout.addWidget(QLabel("Stop Loss Amount:"), 0, 0)
        self.stop_loss_input = QLineEdit("0")
        stop_loss_layout.addWidget(self.stop_loss_input, 0, 1)

        self.stop_loss_price_label = QLabel("Stop Loss @: N/A")
        self.stop_loss_price_label.setStyleSheet("color: red;")
        stop_loss_layout.addWidget(self.stop_loss_price_label, 0, 2)
        
        stop_loss_layout.addWidget(QLabel("Stop Loss Type:"), 1, 0)
        self.stop_loss_type_combo = QComboBox()
        self.stop_loss_type_combo.addItems(["Market", "Limit", "Trailing"])
        self.stop_loss_type_combo.setCurrentText("Trailing")
        stop_loss_layout.addWidget(self.stop_loss_type_combo, 1, 1)
        
        stop_loss_layout.addWidget(QLabel("Stop Loss Calculation:"), 2, 0)
        self.stop_loss_calc_combo = QComboBox()
        self.stop_loss_calc_combo.addItems(["Manual", "ATR"])
        self.stop_loss_calc_combo.setCurrentText("Manual")
        self.stop_loss_calc_combo.currentTextChanged.connect(self.on_stop_loss_calc_changed)
        stop_loss_layout.addWidget(self.stop_loss_calc_combo, 2, 1)

        main_layout.addLayout(stop_loss_layout)

        # ATR layout
        atr_layout = QHBoxLayout()
        atr_layout.addWidget(QLabel("ATR Multiplier:"))
        self.atr_multiplier_input = QDoubleSpinBox()
        self.atr_multiplier_input.setRange(0.1, 100)
        self.atr_multiplier_input.setSingleStep(0.1)
        self.atr_multiplier_input.setValue(10)
        self.atr_multiplier_input.setDecimals(1)
        atr_layout.addWidget(self.atr_multiplier_input)
        self.atr_multiplier_input.textChanged.connect(self.update_atr)
        
        self.atr_label = QLabel("ATR: N/A")
        self.atr_label.setStyleSheet("font-weight: bold; color: blue;")
        atr_layout.addWidget(self.atr_label)
        
        atr_layout.addStretch()
        main_layout.addLayout(atr_layout)
        
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
        
        self.exit_button = QPushButton("EXIT ALL")
        self.exit_button.setStyleSheet("background-color: #ffc107; color: black;")
        self.exit_button.clicked.connect(lambda: self.send_order("exit"))
        button_layout.addWidget(self.exit_button, 1, 0, 1, 2)
        
        main_layout.addLayout(button_layout)


        # Add Take Profit button and quantity spinbox
        tp_layout = QHBoxLayout()
        self.take_profit_button = QPushButton("TAKE PROFIT")
        self.take_profit_button.setStyleSheet("background-color: #28a745; color: black;")
        self.take_profit_button.clicked.connect(self.send_take_profit_order)
        tp_layout.addWidget(self.take_profit_button)

        self.tp_quantity_spinbox = QSpinBox()
        self.tp_quantity_spinbox.setMinimum(1)
        self.tp_quantity_spinbox.setMaximum(1)  # Will be updated dynamically
        tp_layout.addWidget(self.tp_quantity_spinbox)

        button_layout.addLayout(tp_layout, 2, 0, 1, 2)

        # Trade management

        trade_management_layout = QHBoxLayout()
        
        left_buttons = QVBoxLayout()
        self.clear_trade_button = QPushButton("Clear Trade")
        self.clear_trade_button.clicked.connect(self.clear_trade)
        left_buttons.addWidget(self.clear_trade_button)
        
        self.add_trade_button = QPushButton("Add/Update Trade")
        self.add_trade_button.clicked.connect(self.add_or_update_trade)
        left_buttons.addWidget(self.add_trade_button)
        
        right_buttons = QVBoxLayout()
        self.add_tp_button = QPushButton("Add TP")
        self.add_tp_button.clicked.connect(self.add_tp_level)
        right_buttons.addWidget(self.add_tp_button)
        
        self.remove_tp_button = QPushButton("Remove TP")
        self.remove_tp_button.clicked.connect(self.remove_tp_level)
        right_buttons.addWidget(self.remove_tp_button)
        
        trade_management_layout.addLayout(left_buttons)
        trade_management_layout.addStretch()
        trade_management_layout.addLayout(right_buttons)
        
        main_layout.addLayout(trade_management_layout)

        # TP Table
        self.tp_table = TPTableWidget(self)
        self.tp_table_container = QWidget()
        self.tp_table_container.setLayout(QVBoxLayout())
        self.tp_table_container.layout().setContentsMargins(0, 0, 0, 0)
        self.tp_table_container.layout().addWidget(self.tp_table)
        self.tp_table_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        main_layout.addWidget(self.tp_table_container)

        # Trade status label
        status_layout = QHBoxLayout()
        self.trade_status_label = QLabel("Status: Not in trade")
        status_layout.addWidget(self.trade_status_label)

        self.timer_label = QLabel("Time left: 05:00")
        status_layout.addWidget(self.timer_label)
        
        self.action_combo = QComboBox()
        self.action_combo.addItems(["Hold", "Exit", "Reverse"])
        self.action_combo.setCurrentText("Hold")
        status_layout.addWidget(QLabel("Action:"))
        status_layout.addWidget(self.action_combo)
        status_layout.addStretch()
        
        main_layout.addLayout(status_layout)

        # Response area
        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        main_layout.addWidget(self.response_area)

        # Set size policy for the central widget to be expanding
        central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)



        
    def update_contract_type(self):
        contract_type = self.contract_type_combo.currentText()
        if contract_type == "Micros":
            self.symbol_map = {
                "MES": "MES.c.0",
                "MNQ": "MNQ.c.0",
                "MGC": "MGC.c.1",
                "MCL": "MCL.c.0"
            }
            self.ticker_map = {
                "MNQ": "MNQ1!",
                "MGC": "MGCZ2024",
                "MES": "MES1!",
                "MCL": "MCL1!"
            }
            self.default_stop_loss_amounts = {
                "MES": 10,
                "MNQ": 40,
                "MGC": 5,
                "MCL": .30
            }
        else:  # Minis
            self.symbol_map = {
                "ES": "ES.c.0",
                "NQ": "NQ.c.0",
                "GC": "GC.c.1",
                "CL": "CL.c.0"
            }
            self.ticker_map = {
                "NQ": "NQ1!",
                "GC": "GCZ2024",
                "ES": "ES1!",
                "CL": "CL1!"
            }
            self.default_stop_loss_amounts = {
                "ES": 10,
                "NQ": 40,
                "GC": 5,
                "CL": .30
            }
        
        # Update the ticker combo box
        current_ticker = self.ticker_combo.currentText()
        self.ticker_combo.blockSignals(True)
        self.ticker_combo.clear()
        self.ticker_combo.addItems(self.symbol_map.keys())
        if current_ticker in self.symbol_map:
            self.ticker_combo.setCurrentText(current_ticker)
        else:
            self.ticker_combo.setCurrentIndex(0)
        self.ticker_combo.blockSignals(False)
        
        # Update the current ticker and its values
        self.update_default_values(self.ticker_combo.currentText())
        self.update_stop_loss_display(self.ticker_combo.currentText())
        self.update_trade_status()
        self.populate_tp_table()
        self.update_atr()
        if self.is_databento_initialized:
            self.initialize_databento_worker()
    def update_tp_quantity_max(self):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.active_orders:
            max_quantity = self.active_orders[current_ticker]['quantity']
            self.tp_quantity_spinbox.setMaximum(max_quantity)
            self.tp_quantity_spinbox.setEnabled(True)
        else:
            self.tp_quantity_spinbox.setEnabled(False)

    def send_take_profit_order(self):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker not in self.active_orders:
            self.update_response_area("No active trade to take profit from.\n")
            return

        quantity = self.tp_quantity_spinbox.value()
        symbol = self.ticker_map.get(current_ticker, current_ticker)
        current_price = float(self.price_input.text())

        order = {
            "ticker": symbol,
            "action": "exit",
            "orderType": "market",
            "quantity": quantity,
            "price": current_price
        }

        try:
            response = requests.post(self.api_url, json=order)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get("success"):
                self.update_response_area(f"Take Profit order sent successfully for {symbol}. Quantity: {quantity}\n")
                
                # Update the active order
                self.active_orders[current_ticker]['quantity'] -= quantity
                if self.active_orders[current_ticker]['quantity'] <= 0:
                    del self.active_orders[current_ticker]
                    self.update_response_area(f"Position for {current_ticker} fully closed.\n")
                
                self.save_active_orders()
                self.update_trade_status()
                self.update_tp_table()
                self.update_tp_quantity_max()
            else:
                self.update_response_area(f"Error sending Take Profit order: {response_data}\n")
        except requests.RequestException as e:
            self.update_response_area(f"Error sending Take Profit order: {str(e)}\n")

    def stop_all_workers(self):
        if self.databento_worker:
            print("Stopping Databento worker...")
            self.databento_worker.stop()
            self.databento_worker.wait(msecs=5000)  # Wait up to 5 seconds
            if self.databento_worker.isRunning():
                print("Databento worker did not stop gracefully. Terminating...")
                self.databento_worker.terminate()

        if self.archive_worker:
            print("Stopping Archive worker...")
            self.archive_worker.stop()
            self.archive_worker.wait(msecs=5000)  # Wait up to 5 seconds
            if self.archive_worker.isRunning():
                print("Archive worker did not stop gracefully. Terminating...")
                self.archive_worker.terminate()

        if hasattr(self, 'historical_timer'):
            print("Stopping historical timer...")
            self.historical_timer.stop()


    def cleanup(self):
        print("Cleaning up...")
        self.stop_all_workers()
        self.save_settings()
        self.save_active_orders()
        print("Cleanup completed.")

    def closeEvent(self, event):
        event.accept()


    def on_stop_loss_calc_changed(self, calculation_method):
        if calculation_method == "ATR":
            self.stop_loss_input.setReadOnly(True)
            self.atr_multiplier_input.setEnabled(True)
            self.update_atr_stop_loss()
        else:
            self.stop_loss_input.setReadOnly(False)
            self.atr_multiplier_input.setEnabled(False)

    def update_atr_stop_loss(self):
        ticker = self.ticker_combo.currentText()
        atr = self.calculate_atr(ticker)
        if atr == 0:
            self.update_response_area(f"Warning: Using ATR value of 0 for {ticker}. Check data availability.\n")
        multiplier = self.atr_multiplier_input.value()
        stop_loss_amount = atr * multiplier
        self.stop_loss_input.setText(f"{stop_loss_amount:.2f}")
        self.update_stop_loss_display(ticker)


    def map_contract_to_general_symbol(self, contract_symbol):
        # Map contract symbols (e.g., MESZ4) to general symbols (e.g., MES.c.0)
        pattern = r'([A-Z]+)[A-Z]\d'
        match = re.match(pattern, contract_symbol)
        if match:
            base_symbol = match.group(1)
            for key, value in self.symbol_map.items():
                if value.startswith(base_symbol):
                    return value
        return None


    def setup_atr_timer(self):
        self.atr_timer = QTimer(self)
        self.atr_timer.timeout.connect(self.update_atr)
        self.atr_timer.start(60000)  # Update every 60 seconds (1 minute)

    def update_atr(self):
        ticker = self.ticker_combo.currentText()
        atr = self.calculate_atr(ticker)
        self.atr_values[ticker] = atr
        self.atr_label.setText(f"ATR: {atr:.4f}")
        if self.stop_loss_calc_combo.currentText() == "ATR":
            self.update_atr_stop_loss()


    def calculate_atr(self, ticker):
        try:
            symbol = self.symbol_map.get(ticker)
            if not symbol:
                raise ValueError(f"No symbol mapping found for ticker: {ticker}")

            # Find the most recent archived file
            archive_dir = "databento_archives"
            archive_files = sorted([f for f in os.listdir(archive_dir) if f.endswith('.dbn')], reverse=True)
            
            if not archive_files:
                raise ValueError("No archived data files found")

            latest_file = os.path.join(archive_dir, archive_files[0])

            # Read the archived data
            #if os.path.getsize(latest_file) > 0:
            dbn_store = db.read_dbn(latest_file)
            df = dbn_store.to_df(schema="ohlcv-1m")


            # Map contract symbols to general symbols
            df['general_symbol'] = df['symbol'].apply(self.map_contract_to_general_symbol)

            # Filter data for the specific symbol
            df = df[df['general_symbol'] == symbol]

            # Sort the DataFrame by the index (timestamp) in descending order
            df = df.sort_index(ascending=False)

            # Take the latest periods for ATR calculation
            periods_needed = max(self.atr_lookback, self.atr_period * 2)
            df = df.head(periods_needed)

            if df.empty:
                raise ValueError(f"No data returned for {ticker}")

            # Convert nanoseconds to standard units if necessary
            scale_factor = 1e9 if df['high'].max() > 1e6 else 1

            df['high'] = df['high'] / scale_factor
            df['low'] = df['low'] / scale_factor
            df['close'] = df['close'] / scale_factor

            # Reverse the DataFrame back to chronological order for ATR calculation
            df = df.sort_index()

            df['tr1'] = df['high'] - df['low']
            df['tr2'] = abs(df['high'] - df['close'].shift())
            df['tr3'] = abs(df['low'] - df['close'].shift())
            df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['true_range'].rolling(window=self.atr_period).mean()

            atr_value = df['atr'].iloc[-1]
            return atr_value
        except Exception as e:
            self.update_response_area(f"Error calculating ATR for {ticker}: {str(e)}\n")
            return 0

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

        # Add 'Replay Mode' action
        self.replay_mode_action = QAction("Replay Mode", self, checkable=True)
        self.replay_mode_action.triggered.connect(self.toggle_replay_mode)
        preference_menu.addAction(self.replay_mode_action)

        #Enable price udpates
        self.enable_price_updates_action = QAction("Enable Price Updates", self, checkable=True)
        self.enable_price_updates_action.triggered.connect(self.toggle_price_updates)
        preference_menu.addAction(self.enable_price_updates_action)
        # if self.enable_price_updates_action.setChecked(True):
        #     self.toggle_price_updates(True)

        # Add 'Enable OHLCV-1m Archive' action
        self.enable_archive_action = QAction("Enable OHLCV-1m Archive", self, checkable=True)
        self.enable_archive_action.triggered.connect(self.toggle_archive)
        preference_menu.addAction(self.enable_archive_action)
        
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
                        validated_tps = []
                        for tp in tps:
                            if isinstance(tp, dict) and 'target' in tp and 'quantity' in tp:
                                # Ensure 'hit' status is present, default to False if not
                                tp['hit'] = tp.get('hit', False)
                                validated_tps.append(tp)
                        self.tp_levels[ticker] = validated_tps
                
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
        self.update_trade_status(skip_timer_start=True)
        
        # Populate and update TP table
        self.populate_tp_table()
        
        # If in a trade, update entry price and other relevant fields
        if current_ticker in self.active_orders:
            order = self.active_orders[current_ticker]
            self.entry_price = order['entry_price']
            self.price_input.setText(f"{self.entry_price:.2f}")
            self.update_stop_loss_on_startup(current_ticker)
            
            # Calculate remaining time and update timer label
            elapsed_time = time.time() - order['timestamp']
            remaining_time = max(0, self.timer_duration - elapsed_time)
            minutes, seconds = divmod(int(remaining_time), 60)
            self.timer_label.setText(f"Time left: {minutes:02d}:{seconds:02d}")
            
            # Start the timer if there's remaining time
            if remaining_time > 0:
                self.trade_start_time = time.time() - elapsed_time
                self.start_trade_timer()
        else:
            # If not in a trade, use the current price
            current_price = self.current_prices.get(current_ticker, 0)
            self.price_input.setText(f"{current_price:.2f}")
        
        print(f"Updated UI for ticker: {current_ticker}")
        print(f"Active order: {self.active_orders.get(current_ticker)}")
        print(f"TP levels: {self.tp_levels.get(current_ticker)}")

    def update_trade_status(self, skip_timer_start=False):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.active_orders:
            order = self.active_orders[current_ticker]
            entry_price = order['entry_price']
            position_type = "Long" if order['action'] == 'buy' else "Short"
            status_text = f"Status: In trade @ {entry_price:.2f} ({position_type})"
            self.trade_status_label.setText(status_text)
            self.trade_status_label.setStyleSheet("color: green;")
            
            # Start the timer if it's not already running and we're not skipping timer start
            if not skip_timer_start and (self.trade_timer is None or not self.trade_timer.isActive()):
                self.start_trade_timer()
        else:
            self.trade_status_label.setText("Status: Not in trade")
            self.trade_status_label.setStyleSheet("color: red;")
            if self.trade_timer:
                self.trade_timer.stop()
            self.trade_start_time = None
            self.timer_label.setText("Time left: 05:00")
        
        self.update_tp_quantity_max()
        print(f"Updated trade status for {current_ticker}: {'In trade' if current_ticker in self.active_orders else 'Not in trade'}")

    def update_tp_level(self, row, column, new_value):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.tp_levels and row < len(self.tp_levels[current_ticker]):
            tp = self.tp_levels[current_ticker][row]
            if column == 1:  # Quantity
                tp['quantity'] = int(new_value)
            elif column == 2:  # Target
                tp['target'] = float(new_value)
                # Recalculate price if in a trade
                if current_ticker in self.active_orders:
                    entry_price = self.active_orders[current_ticker]['entry_price']
                    action = self.active_orders[current_ticker]['action']
                    if action == 'buy':
                        tp['price'] = entry_price + tp['target']
                    else:  # sell
                        tp['price'] = entry_price - tp['target']
            
            self.save_active_orders()
            self.update_tp_table()  # This will update the price column with the new calculated price
        print(f"Updated TP level: Ticker={current_ticker}, Row={row}, Column={column}, New Value={new_value}")


    def update_tp_table(self):
        if self.tp_table.is_editing:
            return

        self.tp_table.blockSignals(True)
        
        current_ticker = self.ticker_combo.currentText()
        current_price = float(self.price_input.text())
        
        if current_ticker in self.tp_levels and self.tp_levels[current_ticker]:
            tp_levels = self.tp_levels[current_ticker]
            
            for row, tp in enumerate(tp_levels):
                # Update the Price and Status columns
                if current_ticker in self.active_orders:
                    action = self.active_orders[current_ticker]['action']
                    entry_price = self.active_orders[current_ticker]['entry_price']
                    if action == 'buy':
                        tp_price = entry_price + tp['target']
                    else:  # sell
                        tp_price = entry_price - tp['target']
                else:
                    tp_price = current_price + tp['target']
                
                # Price
                price_item = self.tp_table.item(row, 3)
                if price_item:
                    price_item.setText(f"{tp_price:.2f}")
                
                # Status
                status_item = self.tp_table.item(row, 4)
                if status_item:
                    status = "Hit" if tp.get('hit', False) else "Active"
                    status_item.setText(status)
                
                # Apply highlighting to all columns if TP is hit
                highlight_color = QColor(1, 56, 30) if tp.get('hit', False) else self.tp_table.palette().color(QPalette.ColorRole.Base)
                
                for col in range(5):
                    if col == 0:  # Enabled column (QCheckBox)
                        checkbox_widget = self.tp_table.cellWidget(row, col)
                        if checkbox_widget:
                            checkbox_widget.setStyleSheet(f"background-color: {highlight_color.name()}; padding: 2px;")
                            checkbox = checkbox_widget.findChild(QCheckBox)
                            if checkbox:
                                checkbox.setStyleSheet(f"background-color: transparent;")
                    else:
                        item = self.tp_table.item(row, col)
                        if item:
                            item.setBackground(highlight_color)
        
        self.tp_table.blockSignals(False)
        self.adjust_table_size()


    def force_tp_table_update(self):
        print("Forcing TP table update")  # Debug print
        current_ticker = self.ticker_combo.currentText()
        self.tp_table.setRowCount(0)  # Clear the table
        self.populate_tp_table()
        self.update_tp_table()
        self.adjust_table_size()
        QApplication.processEvents()  # Force the GUI to update immediately
        print(f"TP levels after update: {self.tp_levels.get(current_ticker, [])}")      

    def sort_tp_levels(self, ticker):
        if ticker in self.tp_levels:
            self.tp_levels[ticker].sort(key=lambda x: x['target'])

    def populate_tp_table(self):
        current_ticker = self.ticker_combo.currentText()
        self.tp_table.setRowCount(0)  # Clear the table first
        
        if current_ticker in self.tp_levels:
            self.sort_tp_levels(current_ticker)  # Sort the TP levels before populating
            tp_levels = self.tp_levels[current_ticker]
            self.tp_table.setRowCount(len(tp_levels))
            
            for row, tp in enumerate(tp_levels):
                # Enable/Disable checkbox
                checkbox = QCheckBox()
                checkbox.setChecked(tp.get('enabled', True))
                checkbox.stateChanged.connect(lambda state, r=row: self.on_checkbox_changed(r, state))
                checkbox_widget = QWidget()
                checkbox_layout = QHBoxLayout(checkbox_widget)
                checkbox_layout.addWidget(checkbox)
                checkbox_layout.setAlignment(Qt.AlignCenter)
                checkbox_layout.setContentsMargins(0, 0, 0, 0)
                self.tp_table.setCellWidget(row, 0, checkbox_widget)
                
                # Quantity
                quantity_item = QTableWidgetItem(str(tp['quantity']))
                quantity_item.setTextAlignment(Qt.AlignCenter)
                self.tp_table.setItem(row, 1, quantity_item)
                
                # Target
                target_item = QTableWidgetItem(str(tp['target']))
                target_item.setTextAlignment(Qt.AlignCenter)
                self.tp_table.setItem(row, 2, target_item)
                
                # Price
                price_item = QTableWidgetItem(str(tp['price']))
                price_item.setTextAlignment(Qt.AlignCenter)
                self.tp_table.setItem(row, 3, price_item)
                
                # Status
                status = "Hit" if tp.get('hit', False) else "Active"
                status_item = QTableWidgetItem(status)
                status_item.setTextAlignment(Qt.AlignCenter)
                self.tp_table.setItem(row, 4, status_item)
        
        self.update_tp_table()  # Call update_tp_table after populating
        self.adjust_table_size()



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

            #self.update_tp_table()
            self.populate_tp_table
            self.save_active_orders()
            self.force_tp_table_update()  # Force immediate update
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
        self.populate_tp_table()
        self.update_stop_loss_display(ticker)
        self.update_atr()
        
        print(f"Ticker changed to {ticker}") 


    def clear_trade(self, ticker=None):
        print(f"Clear trade called with ticker: {ticker}")
        if ticker is None or ticker == False:
            ticker = self.ticker_combo.currentText()
        print(f"Using ticker: {ticker}")
        if ticker in self.tp_levels:
                for tp in self.tp_levels[ticker]:
                    tp['hit'] = False
        if ticker in self.active_orders:
            del self.active_orders[ticker]
        else:
            self.update_response_area(f"No active trade found for {ticker}.\n")

        self.entry_price = None
        if self.trade_timer:
            self.trade_timer.stop()
        self.trade_start_time = None
        self.timer_label.setText("Time left: 05:00")
        self.update_trade_status()
        self.save_active_orders()
        self.update_tp_table()
        self.update_stop_loss_display(ticker)
        self.update_response_area(f"Trade cleared for {ticker}.\n")
        
        print(f"Active orders after clear: {self.active_orders}")

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
            
            # Start the timer when a new trade is added
            self.start_trade_timer()

            if current_ticker not in self.tp_levels:
                self.tp_levels[current_ticker] = []
            
            # Update prices for existing TP levels
            for tp in self.tp_levels[current_ticker]:
                if action == 'buy':
                    tp['price'] = entry_price + tp['target']
                else:  # sell
                    tp['price'] = entry_price - tp['target']
            
            self.save_active_orders()
            self.update_trade_status()
            self.update_tp_table()
            self.update_tp_quantity_max()
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


    def check_stop_loss(self, ticker, current_price):
        if ticker not in self.active_orders:
            return False

        order = self.active_orders[ticker]
        entry_price = order['entry_price']
        action = order['action']
        stop_loss = order.get('stop_loss')

        if not stop_loss:
            return False

        stop_type = stop_loss.get('type')
        stop_price = stop_loss.get('stopPrice')
        trail_amount = stop_loss.get('trailAmount')

        if stop_type == 'stop' or stop_type == 'stop_limit':
            if stop_price is None:
                return False
            if action == 'buy' and current_price <= stop_price:
                return True
            elif action == 'sell' and current_price >= stop_price:
                return True
        elif stop_type == 'trailing_stop':
            if trail_amount is None:
                return False
            if action == 'buy':
                if stop_price is None:
                    stop_price = entry_price - trail_amount
                new_stop_price = max(current_price - trail_amount, stop_price)
                if current_price <= new_stop_price:
                    return True
                if new_stop_price > stop_price:
                    stop_loss['stopPrice'] = new_stop_price
            elif action == 'sell':
                if stop_price is None:
                    stop_price = entry_price + trail_amount
                new_stop_price = min(current_price + trail_amount, stop_price)
                if current_price >= new_stop_price:
                    return True
                if new_stop_price < stop_price:
                    stop_loss['stopPrice'] = new_stop_price

        return False
    
    def start_trade_timer(self):
        self.trade_start_time = time.time()
        self.timer_expired_message_shown = False  # Reset the flag when starting a new timer
        if self.trade_timer is None:
            self.trade_timer = QTimer(self)
            self.trade_timer.timeout.connect(self.update_trade_timer)
        self.trade_timer.start(1000)  # Update every second

    # def update_trade_timer(self):
    #     if self.trade_start_time is None:
    #         return
        
    #     elapsed_time = time.time() - self.trade_start_time
    #     remaining_time = max(0, self.timer_duration - elapsed_time)
        
    #     minutes, seconds = divmod(int(remaining_time), 60)
    #     self.timer_label.setText(f"Time left: {minutes:02d}:{seconds:02d}")
        
    #     if remaining_time <= 0:
    #         self.trade_timer.stop()
    #         self.check_exit_condition()

    def update_trade_timer(self):
        if self.trade_start_time is None:
            return
        
        elapsed_time = time.time() - self.trade_start_time
        remaining_time = max(0, self.timer_duration - elapsed_time)
        
        minutes, seconds = divmod(int(remaining_time), 60)
        self.timer_label.setText(f"Time left: {minutes:02d}:{seconds:02d}")
        
        if remaining_time <= 0:
            self.check_exit_condition()
        
        # Always restart the timer to continue checking
        self.trade_timer.start(1000)


    def check_exit_condition(self):
        current_ticker = self.ticker_combo.currentText()
        if current_ticker in self.active_orders:
            current_price = float(self.price_input.text())
            entry_price = self.active_orders[current_ticker]['entry_price']
            action = self.active_orders[current_ticker]['action']
            selected_action = self.action_combo.currentText()
            
            # Check if the trade is in profit
            is_in_profit = (action == 'buy' and current_price > entry_price) or (action == 'sell' and current_price < entry_price)
            
            if selected_action in ["Exit", "Reverse"]:
                if not is_in_profit:
                    if selected_action == "Exit":
                        self.send_order("exit")
                        self.update_response_area("Timer expired. Not in profit. Exiting trade.\n")
                    else:  # Reverse
                        self.reverse_trade(current_ticker, current_price, action)
                        self.update_response_area("Timer expired. Not in profit. Reversing trade.\n")
                    self.timer_expired_message_shown = False  # Reset the flag after action
                elif not self.timer_expired_message_shown:
                    self.update_response_area(f"Timer expired. In profit. Holding trade ({selected_action} not executed).\n")
                    self.timer_expired_message_shown = True
            elif selected_action == "Hold" and not self.timer_expired_message_shown:
                self.update_response_area("Timer expired. Holding trade as per selected action.\n")
                self.timer_expired_message_shown = True
        else:
            self.update_response_area("No active trade to check exit condition.\n")


    # def check_exit_condition(self):
    #     current_ticker = self.ticker_combo.currentText()
    #     if current_ticker in self.active_orders:
    #         current_price = float(self.price_input.text())
    #         entry_price = self.active_orders[current_ticker]['entry_price']
    #         action = self.active_orders[current_ticker]['action']
    #         selected_action = self.action_combo.currentText()
            
    #         # Check if the trade is in profit
    #         is_in_profit = (action == 'buy' and current_price > entry_price) or (action == 'sell' and current_price < entry_price)
            
    #         if selected_action in ["Exit", "Reverse"]:
    #             if not is_in_profit:
    #                 if selected_action == "Exit":
    #                     self.send_order("exit")
    #                     self.update_response_area("Timer expired. Not in profit. Exiting trade.\n")
    #                 else:  # Reverse
    #                     self.reverse_trade(current_ticker, current_price, action)
    #                     self.update_response_area("Timer expired. Not in profit. Reversing trade.\n")
    #             else:
    #                 self.update_response_area(f"Timer expired. In profit. Holding trade ({selected_action} not executed).\n")
    #         else:  # Hold
    #             self.update_response_area("Timer expired. Holding trade as per selected action.\n")
            
    #         # Restart the timer
    #         self.start_trade_timer()
    #     else:
    #         self.update_response_area("No active trade to check exit condition.\n")



    def reverse_trade(self, ticker, current_price, current_action):
        # First, exit the current trade
        self.send_order("exit")
        self.update_response_area(f"Exiting current trade for {ticker}.\n")

        # Determine the new action (opposite of the current action)
        new_action = 'sell' if current_action == 'buy' else 'buy'

        # Get the current stop loss settings
        stop_loss_amount = float(self.stop_loss_input.text())
        stop_loss_type = self.stop_loss_type_combo.currentText()

        # Calculate the new stop loss
        if stop_loss_type == "Trailing":
            stop_loss_info = {
                "type": "trailing_stop",
                "trailAmount": stop_loss_amount
            }
        else:
            if new_action == "buy":
                stop_loss_price = current_price - stop_loss_amount
            else:  # sell
                stop_loss_price = current_price + stop_loss_amount
            
            stop_loss_info = {
                "type": self.get_stop_loss_type(stop_loss_type),
                "stopPrice": stop_loss_price
            }

        # Enter a new trade in the opposite direction
        new_order = {
            "ticker": self.ticker_map.get(ticker, ticker),
            "action": new_action,
            "orderType": "market",
            "limitPrice": current_price,
            "quantity": self.quantity_input.value(),
            "stopLoss": stop_loss_info  # Include the stop loss information
        }

        # Send the new order
        response_text = self.send_order_to_server(new_order)
        if "success" in response_text.lower():
            self.active_orders[ticker] = {
                "symbol": ticker,
                "action": new_action,
                "quantity": self.quantity_input.value(),
                "entry_price": current_price,
                "timestamp": int(time.time()),
                "stop_loss": stop_loss_info  # Store stop loss info
            }
            self.save_active_orders()
            self.update_trade_status()
            self.adjust_tp_levels_on_reverse(ticker, current_price, new_action)
            self.update_tp_table()
            self.update_stop_loss_display(ticker)
            self.start_trade_timer()  # Restart the timer for the new trade
            self.update_response_area(f"Reversed trade for {ticker}. New action: {new_action}, Entry price: {current_price}\n")
            self.update_response_area(f"Stop loss set: {stop_loss_info['type']} @ {stop_loss_info.get('stopPrice', stop_loss_info.get('trailAmount')):.2f}\n")
        else:
            self.update_response_area(f"Failed to reverse trade for {ticker}. Error: {response_text}\n")



    def adjust_tp_levels(self, ticker, entry_price, action):
        if ticker in self.tp_levels:
            adjusted_tp_levels = []
            for tp in self.tp_levels[ticker]:
                new_tp = tp.copy()
                new_tp['hit'] = False  # Reset hit status
                if action == 'buy':
                    new_tp['price'] = entry_price + abs(new_tp['target'])
                else:  # sell
                    new_tp['price'] = entry_price - abs(new_tp['target'])
                adjusted_tp_levels.append(new_tp)
            
            self.tp_levels[ticker] = adjusted_tp_levels
            self.save_active_orders()  # Save the updated TP levels
            self.update_response_area(f"Adjusted TP levels for new {action} trade on {ticker}.\n")


    def adjust_tp_levels_on_reverse(self, ticker, new_entry_price, new_action):
        if ticker in self.tp_levels:
            adjusted_tp_levels = []
            for tp in self.tp_levels[ticker]:
                new_tp = tp.copy()
                new_tp['hit'] = False  # Reset hit status
                if new_action == 'buy':
                    new_tp['target'] = abs(new_tp['target'])  # Make target positive for long trades
                    new_tp['price'] = new_entry_price + new_tp['target']
                else:  # sell
                    new_tp['target'] = -abs(new_tp['target'])  # Make target negative for short trades
                    new_tp['price'] = new_entry_price + new_tp['target']
                adjusted_tp_levels.append(new_tp)
            
            self.tp_levels[ticker] = adjusted_tp_levels
            self.save_active_orders()  # Save the updated TP levels
            self.update_response_area(f"Adjusted TP levels for reversed trade on {ticker}.\n")


    def delayed_tp_check(self):
        for ticker in self.active_orders.keys():
            current_price = self.current_prices.get(ticker)
            if current_price is not None and current_price != 0:
                self.check_and_update_tp_levels(ticker, current_price)
                self.update_stop_loss(ticker, current_price)  # Add this line
            else:
                print(f"Skipping TP check for {ticker} due to invalid price")
        self.update_response_area("Initial TP check completed.\n")


    def update_stop_loss(self, ticker, current_price):
        if ticker in self.active_orders:
            order = self.active_orders[ticker]
            stop_loss = order.get('stop_loss')
            if stop_loss:
                if self.check_stop_loss(ticker, current_price):
                    # Stop loss hit, send exit order
                    exit_order = {
                        "ticker": self.ticker_map.get(ticker, ticker),
                        "action": "exit",
                        "orderType": "market"
                        #"quantity": order['quantity']  # Exit the full position
                    }
                    try:
                        response = requests.post(self.api_url, json=exit_order)
                        response.raise_for_status()
                        
                        response_data = response.json()
                        if response_data.get("success"):
                            self.update_response_area(f"Stop loss hit for {ticker} at price {current_price:.2f}. Exit order sent.\n")
                            # Remove the order from active orders
                            del self.active_orders[ticker]
                            self.save_active_orders()
                            self.update_trade_status()
                            self.update_tp_table()
                        else:
                            self.update_response_area(f"Error sending exit order for stop loss: {response_data}\n")
                    except requests.RequestException as e:
                        self.update_response_area(f"Error sending exit order for stop loss: {str(e)}\n")
                else:
                    self.update_stop_loss_display(ticker)
            else:
                print(f"No stop loss set for {ticker}")
        else:
            print(f"No active order for {ticker}")

    
    def execute_tp_order(self, ticker, tp):
        self.update_response_area(f"TP hit for {ticker}: {tp['quantity']} @ {tp['price']:.2f}\n")
        
        if ticker in self.active_orders:
            # Send exit order
            exit_order = {
                "ticker": self.ticker_map.get(ticker, ticker),
                "action": "exit",
                "orderType": "market",
                "quantity": tp['quantity'],
                "price": tp['price']
            }
            
            try:
                response = requests.post(self.api_url, json=exit_order)
                response.raise_for_status()
                
                response_data = response.json()
                if response_data.get("success"):
                    self.update_response_area(f"Exit order sent for TP: {ticker}, Quantity: {tp['quantity']}, Price: {tp['price']:.2f}\n")
                    
                    # Update the active order
                    self.active_orders[ticker]['quantity'] -= tp['quantity']
                    if self.active_orders[ticker]['quantity'] <= 0:
                        del self.active_orders[ticker]
                        self.update_response_area(f"Order for {ticker} fully closed and removed from active orders.\n")
                else:
                    self.update_response_area(f"Error sending exit order for TP: {response_data}\n")
            except requests.RequestException as e:
                self.update_response_area(f"Error sending exit order for TP: {str(e)}\n")
        self.update_tp_quantity_max()  # Add this line to update the TP quantity spinbox
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
            self.save_active_orders()
            self.force_tp_table_update()
            #self.adjust_table_size()
            print(f"Removed TP level: {removed_tp}")
        else:
            print("Invalid row selected for removal")


    def check_and_update_tp_levels(self, ticker, current_price):
        if ticker not in self.tp_levels or ticker not in self.active_orders:
            return

        order = self.active_orders[ticker]
        action = order['action']
        entry_price = order['entry_price']

        for tp in self.tp_levels[ticker]:
            if tp['enabled'] and not tp['hit']:
                tp_price = tp['price']
                
                if (action == 'buy' and current_price >= tp_price) or \
                   (action == 'sell' and current_price <= tp_price):
                    tp['hit'] = True
                    self.execute_tp_order(ticker, tp)
                else:
                    print(f"TP for {ticker} not hit: Current price {current_price}, TP price {tp_price}, Entry price {entry_price}")

        self.update_tp_table()


    def handle_databento_data(self, subscription_id, message):
        try:
            if isinstance(message, db.SystemMsg):
                # Handle system messages (like Heartbeat)
                print(f"Received system message: {message.msg}")
                return  # Skip further processing for system messages

            if subscription_id == "historical":
                ticker = self.ticker_combo.currentText()
                if hasattr(message, 'close'):
                    price = message.close / 1000000000  # Adjust scale factor if needed
                else:
                    print(f"Unexpected message format: {message}")
                    return
            else:
                if hasattr(message, 'instrument_id'):
                    instrument_id = message.instrument_id
                    symbol = self.instrument_id_map.get(instrument_id)
                    ticker = next((key for key, value in self.symbol_map.items() if value == symbol), None)
                    if hasattr(message, 'close'):
                        price = message.close / 1000000000  # Adjust scale factor if needed
                    else:
                        print(f"Unexpected message format: {message}")
                        return
                else:
                    print(f"Unexpected message format: {message}")
                    return

            if ticker:
                self.current_prices[ticker] = price
                if ticker == self.ticker_combo.currentText():
                    self.price_input.setText(f"{price:.2f}")
                    self.update_tp_table()

                    # Check and update stop loss
                    if ticker in self.active_orders:
                        if self.check_stop_loss(ticker, price):
                            # Stop loss hit, send exit order
                            exit_order = {
                                "ticker": self.ticker_map.get(ticker, ticker),
                                "action": "exit",
                                "orderType": "market",
                            }
                            try:
                                response = requests.post(self.api_url, json=exit_order)
                                response.raise_for_status()
                                
                                response_data = response.json()
                                if response_data.get("success"):
                                    self.update_response_area(f"Stop loss hit for {ticker} at price {price:.2f}. Exit order sent.\n")
                                    del self.active_orders[ticker]
                                    self.save_active_orders()
                                    self.update_trade_status()
                                    self.update_tp_table()
                                else:
                                    self.update_response_area(f"Error sending exit order for stop loss: {response_data}\n")
                            except requests.RequestException as e:
                                self.update_response_area(f"Error sending exit order for stop loss: {str(e)}\n")
                            self.clear_trade(ticker)
                        else:
                            self.update_stop_loss_display(ticker)
                    
                    # Check and execute TPs
                    if ticker in self.tp_levels:
                        for tp in self.tp_levels[ticker]:
                            if tp['enabled'] and not tp['hit']:
                                if ticker in self.active_orders:
                                    action = self.active_orders[ticker]['action']
                                    if (action == 'buy' and price >= tp['price']) or \
                                    (action == 'sell' and price <= tp['price']):
                                        tp['hit'] = True
                                        self.execute_tp_order(ticker, tp)
                                        self.update_tp_table()
                
                self.update_tp_table()  # Update again after potential TP executions
                        
        except Exception as e:
            print(f"Error processing data: {type(e).__name__}: {str(e)}")
            print(f"Message: {message}")


    def toggle_archive(self, state):
        if state:
            if not self.archive_key:
                QMessageBox.warning(self, "Archive Key Missing", "Please set the Archive Key in settings before enabling archiving.")
                self.enable_archive_action.setChecked(False)
                return

            if not self.archive_worker:
                self.archive_worker = ArchiveWorker(self.archive_key)
                self.archive_worker.error_signal.connect(self.handle_archive_error)
            
            self.archive_worker.start()
            self.update_response_area("OHLCV-1m archiving started.\n")
        else:
            if self.archive_worker:
                self.archive_worker.stop()
                self.archive_worker.wait()
                self.archive_worker = None
            self.update_response_area("OHLCV-1m archiving stopped.\n")

    def handle_archive_error(self, error_msg):
        self.update_response_area(f"Archive error: {error_msg}\n")

    def open_settings(self):
        dialog = SettingsDialog(self, self.api_url, self.databento_key, self.archive_key, self.atr_period, self.atr_lookback)
        if dialog.exec_() == QDialog.Accepted:
            self.api_url, self.databento_key, self.archive_key, self.atr_period, self.atr_lookback = dialog.get_settings()
            self.save_settings()
            self.update_response_area(f"Settings updated:\nWebhook URL: {self.api_url}\n"
                                      f"Databento API Key: {'*' * len(self.databento_key)}\n"
                                      f"Archive Key: {'*' * len(self.archive_key)}\n"
                                      f"ATR Period: {self.atr_period}\n"
                                      f"ATR Lookback: {self.atr_lookback} minutes\n")
            self.initialize_databento_worker()


    def load_settings(self):
        if os.path.exists('settings.json'):
            try:
                with open('settings.json', 'r') as f:
                    settings = json.load(f)
                    self.api_url = settings.get('api_url', "https://your-api-endpoint.com/orders")
                    self.databento_key = settings.get('databento_key', "")
                    self.archive_key = settings.get('archive_key', "")
                    self.atr_period = settings.get('atr_period', 14)
                    self.atr_lookback = settings.get('atr_lookback', 390)
                print(f"Loaded settings: API URL: {self.api_url}, Databento Key: {'*' * len(self.databento_key)}, Archive Key: {'*' * len(self.archive_key)}")
            except json.JSONDecodeError:
                print("Error loading settings.json. Using default settings.")
                self.use_default_settings()
        else:
            print("settings.json not found. Using default settings.")
            self.use_default_settings()


    def use_default_settings(self):
        self.api_url = "https://your-api-endpoint.com/orders"
        self.databento_key = ""
        self.archive_key = ""
        self.atr_period = 14
        self.atr_lookback = 390

    def save_settings(self):
        settings = {
            'api_url': self.api_url,
            'databento_key': self.databento_key,
            'archive_key': self.archive_key,
            'atr_period': self.atr_period,
            'atr_lookback': self.atr_lookback
        }
        with open('settings.json', 'w') as f:
            json.dump(settings, f, indent=2)

    
    def initialize_price_and_stoploss(self):
        self.update_contract_type()  # Add this li
        initial_ticker = self.ticker_combo.currentText()
        self.update_default_values(initial_ticker)
        
        for ticker in self.active_orders.keys():
            self.update_stop_loss_display(ticker)

        # If there's no active order for the initial ticker, still update its display
        if initial_ticker not in self.active_orders:
            self.update_stop_loss_display(initial_ticker)


    def update_default_values(self, ticker):
        default_stop_loss = self.default_stop_loss_amounts.get(ticker, 0)
        self.stop_loss_input.setText(str(default_stop_loss))
        print(f"Updated default stop loss for {ticker} to {default_stop_loss}")  # Add this line for debugging

    def get_stop_loss_type(self, gui_type):
        if gui_type == "Market":
            return "stop"
        elif gui_type == "Limit":
            return "stop_limit"
        elif gui_type == "Trailing":
            return "trailing_stop"
        else:
            return "stop"


    def get_stop_loss_gui_type(self, stop_type):
        if stop_type == 'stop':
            return "Market"
        elif stop_type == 'stop_limit':
            return "Limit"
        elif stop_type == 'trailing_stop':
            return "Trailing"
        else:
            print(f"Unknown stop type: {stop_type}. Defaulting to Market.")
            return "Market"


    def update_stop_loss_on_startup(self, ticker):
        if ticker in self.active_orders:
            order = self.active_orders[ticker]
            stop_loss = order.get('stop_loss')

            if stop_loss:
                stop_type = stop_loss['type']
                if stop_type == 'trailing_stop':
                    trail_amount = stop_loss['trailAmount']
                    self.stop_loss_input.setText(str(trail_amount))
                else:
                    stop_price = stop_loss.get('stopPrice')
                    if stop_price is not None:
                        self.stop_loss_input.setText(str(abs(order['entry_price'] - stop_price)))
                    else:
                        print(f"Warning: No stop price found for {ticker}")
                        self.stop_loss_input.setText("0")

                self.stop_loss_type_combo.setCurrentText(self.get_stop_loss_gui_type(stop_type))
                self.update_stop_loss_display(ticker)
            else:
                print(f"No stop loss set for {ticker}")
                self.stop_loss_input.setText("0")
                self.stop_loss_type_combo.setCurrentText("Market")
        else:
            print(f"No active order for {ticker}")
            self.stop_loss_input.setText("0")
            self.stop_loss_type_combo.setCurrentText("Market")


    def update_stop_loss_display(self, ticker=None):
        if ticker is None:
            ticker = self.ticker_combo.currentText()
        
        if ticker in self.active_orders:
            order = self.active_orders[ticker]
            stop_loss = order.get('stop_loss')
            current_price = self.current_prices.get(ticker, order['entry_price'])
            
            if stop_loss:
                stop_type = stop_loss['type']
                if stop_type == 'trailing_stop':
                    trail_amount = stop_loss['trailAmount']
                    stop_price = stop_loss.get('stopPrice')
                    if stop_price is None:
                        if order['action'] == 'buy':
                            stop_price = order['entry_price'] - trail_amount
                        else:  # sell
                            stop_price = order['entry_price'] + trail_amount
                    self.stop_loss_price_label.setText(f"Stop Loss @: {stop_price:.2f} (Trailing)")
                else:
                    stop_price = stop_loss['stopPrice']
                    self.stop_loss_price_label.setText(f"Stop Loss @: {stop_price:.2f}")
                
                self.stop_loss_price_label.setStyleSheet("color: red;")
            else:
                if self.stop_loss_calc_combo.currentText() == "ATR":
                    atr = self.atr_values.get(ticker, 0)
                    multiplier = self.atr_multiplier_input.value()
                    stop_loss_amount = atr * multiplier
                    if order['action'] == 'buy':
                        stop_price = order['entry_price'] - stop_loss_amount
                    else:  # sell
                        stop_price = order['entry_price'] + stop_loss_amount
                    self.stop_loss_price_label.setText(f"Stop Loss @: {stop_price:.2f} (ATR)")
                else:
                    self.stop_loss_price_label.setText("Stop Loss @: N/A")
                self.stop_loss_price_label.setStyleSheet("color: red;")
        else:
            if self.stop_loss_calc_combo.currentText() == "ATR":
                atr = self.atr_values.get(ticker, 0)
                multiplier = self.atr_multiplier_input.value()
                stop_loss_amount = atr * multiplier
                current_price = float(self.price_input.text())
                stop_price = current_price - stop_loss_amount
                self.stop_loss_price_label.setText(f"Stop Loss @: {stop_price:.2f} (ATR)")
                self.stop_loss_price_label.setStyleSheet("color: red;")
            else:
                default_stop_loss = self.default_stop_loss_amounts.get(ticker, 0)
                self.stop_loss_input.setText(str(default_stop_loss))
                self.stop_loss_price_label.setText("Stop Loss @: N/A")
                self.stop_loss_price_label.setStyleSheet("color: gray;") 

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
                stop_loss_info = {
                    "type": "trailing_stop",
                    "trailAmount": stop_loss_amount
                }
            else:
                if action == "buy":
                    stop_loss_price = current_price - stop_loss_amount
                else:  # sell
                    stop_loss_price = current_price + stop_loss_amount
                
                stop_loss_info = {
                    "type": self.get_stop_loss_type(stop_loss_type),
                    "stopPrice": stop_loss_price
                }
            
            order["stopLoss"] = stop_loss_info
        
        response_text = self.send_order_to_server(order)
        
        if "success" in response_text.lower():
            if action == "exit":
                if ticker in self.active_orders:
                    del self.active_orders[ticker]
                    self.save_active_orders()
                    response_text += f"Removed order for {ticker} from active orders.\n"
            else:  # buy or sell
                if ticker in self.active_orders:
                    # Updating existing order
                    existing_order = self.active_orders[ticker]
                    new_quantity = existing_order['quantity'] + quantity
                    weighted_entry_price = (existing_order['entry_price'] * existing_order['quantity'] + current_price * quantity) / new_quantity
                    
                    self.active_orders[ticker].update({
                        "quantity": new_quantity,
                        "entry_price": weighted_entry_price,
                        "timestamp": int(time.time()),
                        "stop_loss": stop_loss_info  # Update stop loss info
                    })
                    
                    response_text += f"Updated existing {action} position for {symbol}.\n"
                    response_text += f"New Total Quantity: {new_quantity}\n"
                    response_text += f"New Weighted Entry Price: {weighted_entry_price:.2f}\n"
                else:
                    # New order
                    self.active_orders[ticker] = {
                        "symbol": ticker,
                        "action": action,
                        "quantity": quantity,
                        "entry_price": current_price,
                        "timestamp": int(time.time()),
                        "stop_loss": stop_loss_info  # Store stop loss info
                    }
                    response_text += f"New {action} position opened for {symbol}.\n"
                
                self.save_active_orders()
                self.adjust_tp_levels(ticker, current_price, action)
            
            self.update_trade_status()
            self.update_tp_table()
            self.update_stop_loss_display(ticker)
        
        # Add stop loss details to the response text
        if "stopLoss" in order:
            sl_info = order["stopLoss"]
            if sl_info["type"] == "trailing_stop":
                response_text += f"Stop Loss: Trailing {sl_info['trailAmount']:.2f}\n"
            else:
                response_text += f"Stop Loss: {sl_info['type'].capitalize()} @ {sl_info['stopPrice']:.2f}\n"
        
        self.update_response_area(response_text)

    def send_order_to_server(self, order):
        try:
            response = requests.post(self.api_url, json=order)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get("success"):
                response_text = f"{order['action'].capitalize()} order sent successfully for {order['ticker']}!\n"
                response_text += f"Quantity: {order['quantity']}\n"
                response_text += f"Price: {order['limitPrice']:.2f}\n"
                if "stopLoss" in order:
                    sl_info = order["stopLoss"]
                    if sl_info["type"] == "trailing_stop":
                        response_text += f"Stop Loss: Trailing {sl_info['trailAmount']:.2f}\n"
                    else:
                        response_text += f"Stop Loss: {sl_info['type'].capitalize()} @ {sl_info['stopPrice']:.2f}\n"
            else:
                response_text = f"Error sending {order['action']} order for {order['ticker']}: Unsuccessful response from server\n"
                response_text += f"Response: {json.dumps(response_data, indent=2)}\n"
            
            return response_text
        except requests.RequestException as e:
            return f"Error sending {order['action']} order for {order['ticker']}: {str(e)}\n" 
    
    # def send_order(self, action):
    #     ticker = self.ticker_combo.currentText()
    #     symbol = self.ticker_map.get(ticker, ticker)

    #     try:
    #         current_price = float(self.price_input.text())
    #         quantity = self.quantity_input.value()
    #         stop_loss_amount = float(self.stop_loss_input.text())
    #     except ValueError:
    #         self.update_response_area("Error: Invalid input for price or stop loss.\n")
    #         return
        
    #     order = {
    #         "ticker": symbol,
    #         "action": action,
    #         "orderType": "market",
    #         "limitPrice": current_price,
    #         "quantity": quantity
    #     }
        
    #     # ... [stop loss logic remains the same] ...
        
    #     response_text = self.send_order_to_server(order)
        
    #     if "success" in response_text.lower():
    #         if action == "exit":
    #             if ticker in self.active_orders:
    #                 del self.active_orders[ticker]
    #                 self.save_active_orders()
    #                 response_text += f"Removed order for {ticker} from active orders.\n"
    #         else:  # buy or sell
    #             if ticker in self.active_orders:
    #                 # Updating existing order
    #                 existing_order = self.active_orders[ticker]
    #                 new_quantity = existing_order['quantity'] + quantity
    #                 weighted_entry_price = (existing_order['entry_price'] * existing_order['quantity'] + current_price * quantity) / new_quantity
                    
    #                 self.active_orders[ticker].update({
    #                     "quantity": new_quantity,
    #                     "entry_price": weighted_entry_price,
    #                     "timestamp": int(time.time()),
    #                     "stop_loss": order.get("stopLoss")  # Update stop loss info
    #                 })
                    
    #                 response_text += f"Updated existing {action} position for {symbol}.\n"
    #                 response_text += f"New Total Quantity: {new_quantity}\n"
    #                 response_text += f"New Weighted Entry Price: {weighted_entry_price:.2f}\n"
    #             else:
    #                 # New order
    #                 self.active_orders[ticker] = {
    #                     "symbol": ticker,
    #                     "action": action,
    #                     "quantity": quantity,
    #                     "entry_price": current_price,
    #                     "timestamp": int(time.time()),
    #                     "stop_loss": order.get("stopLoss")  # Store stop loss info
    #                 }
    #                 response_text += f"New {action} position opened for {symbol}.\n"
                
    #             self.save_active_orders()
    #             self.adjust_tp_levels(ticker, current_price, action)
            
    #         self.update_trade_status()
    #         self.update_tp_table()
    #         self.update_stop_loss_display(ticker)
        
    #     self.update_response_area(response_text)
    
    # def send_order(self, action):
    #     ticker = self.ticker_combo.currentText()
    #     symbol = self.ticker_map.get(ticker, ticker)

    #     try:
    #         current_price = float(self.price_input.text())
    #         quantity = self.quantity_input.value()
    #         stop_loss_amount = float(self.stop_loss_input.text())
    #     except ValueError:
    #         self.update_response_area("Error: Invalid input for price or stop loss.\n")
    #         return
        
    #     order = {
    #         "ticker": symbol,
    #         "action": action,
    #         "orderType": "market",
    #         "limitPrice": current_price,
    #         "quantity": quantity
    #     }
        
    #     response_text = self.send_order_to_server(order)
        
    #     if "success" in response_text.lower():
    #         if action == "exit":
    #             if ticker in self.active_orders:
    #                 del self.active_orders[ticker]
    #                 self.save_active_orders()
    #                 response_text += f"Removed order for {ticker} from active orders.\n"
    #         else:  # buy or sell
    #             self.active_orders[ticker] = {
    #                 "symbol": ticker,
    #                 "action": action,
    #                 "quantity": quantity,
    #                 "entry_price": current_price,
    #                 "timestamp": int(time.time()),
    #                 "stop_loss": order.get("stopLoss")  # Store stop loss info
    #             }
    #             self.save_active_orders()
            
    #         self.update_trade_status()
    #         self.update_tp_table()
    #         self.update_stop_loss_display(ticker)
        
    #     self.update_response_area(response_text)


    # def send_order(self, action):
    #     ticker = self.ticker_combo.currentText()
    #     symbol = self.ticker_map.get(ticker, ticker)

    #     try:
    #         current_price = float(self.price_input.text())
    #         quantity = self.quantity_input.value()
    #         stop_loss_amount = float(self.stop_loss_input.text())
    #     except ValueError:
    #         self.update_response_area("Error: Invalid input for price or stop loss.\n")
    #         return
        
    #     order = {
    #         "ticker": symbol,
    #         "action": action,
    #         "orderType": "market",
    #         "limitPrice": current_price,
    #         "quantity": quantity
    #     }
        
    #     if action in ["buy", "sell"]:
    #         if ticker in self.active_orders:
    #             # Adding to an existing position
    #             existing_order = self.active_orders[ticker]
    #             if existing_order['action'] != action:
    #                 self.update_response_area(f"Error: Cannot {action} when current position is {existing_order['action']}.\n")
    #                 return
                
    #             # Use the existing stop loss
    #             order["stopLoss"] = existing_order['stop_loss']
                
    #             response_text = self.send_order_to_server(order)
    #             if "success" in response_text.lower():
    #                 # Update the existing order
    #                 new_quantity = existing_order['quantity'] + quantity
    #                 weighted_entry_price = (existing_order['entry_price'] * existing_order['quantity'] + current_price * quantity) / new_quantity
                    
    #                 self.active_orders[ticker].update({
    #                     "quantity": new_quantity,
    #                     "entry_price": weighted_entry_price,
    #                     "timestamp": int(time.time())
    #                 })
                    
    #                 response_text += f"Added to existing {action} position for {symbol}.\n"
    #                 response_text += f"New Total Quantity: {new_quantity}\n"
    #                 response_text += f"New Weighted Entry Price: {weighted_entry_price:.2f}\n"
                    
    #                 self.save_active_orders()
    #                 self.update_trade_status()
    #                 self.update_tp_table()
    #                 self.update_stop_loss_display(ticker)
                
    #             self.update_response_area(response_text)
    #             return
            
    #         # New position
    #         stop_loss_type = self.stop_loss_type_combo.currentText()
    #         if stop_loss_type == "Trailing":
    #             stop_loss_info = {
    #                 "type": "trailing_stop",
    #                 "trailAmount": stop_loss_amount
    #             }
    #         else:
    #             if action == "buy":
    #                 stop_loss_price = current_price - stop_loss_amount
    #             else:  # sell
    #                 stop_loss_price = current_price + stop_loss_amount
                
    #             stop_loss_info = {
    #                 "type": self.get_stop_loss_type(stop_loss_type),
    #                 "stopPrice": stop_loss_price
    #             }
            
    #         order["stopLoss"] = stop_loss_info
        
    #     response_text = self.send_order_to_server(order)
        
    #     if "success" in response_text.lower():
    #         if action != "exit":
    #             self.active_orders[ticker] = {
    #                 "symbol": ticker,
    #                 "action": action,
    #                 "quantity": quantity,
    #                 "entry_price": current_price,
    #                 "timestamp": int(time.time()),
    #                 "stop_loss": order.get("stopLoss")  # Store stop loss info
    #             }
    #             # Update TP prices
    #             if ticker in self.tp_levels:
    #                 for tp in self.tp_levels[ticker]:
    #                     if action == "buy":
    #                         tp['price'] = current_price + tp['target']
    #                         tp['hit'] = False
    #                     else:  # sell
    #                         tp['price'] = current_price - tp['target']
    #                         tp['hit'] = False

    #             self.save_active_orders()
            
    #         if action == "exit":
    #             if ticker in self.active_orders:
    #                 del self.active_orders[ticker]
    #                 self.save_active_orders()
    #                 response_text += f"Removed order for {ticker} from active orders.\n"
            
    #         self.update_trade_status()
    #         self.update_tp_table()
    #         self.update_stop_loss_display(ticker)
        
    #     self.update_response_area(response_text)

    # def send_order_to_server(self, order):
    #     try:
    #         response = requests.post(self.api_url, json=order)
    #         response.raise_for_status()
            
    #         response_data = response.json()
    #         if response_data.get("success"):
    #             response_text = f"{order['action'].capitalize()} order sent successfully for {order['ticker']}!\n"
    #             if order['action'] != "exit":
    #                 response_text += f"Entry Price: {order['limitPrice']}\n"
    #             if "stopLoss" in order:
    #                 stop_loss_info = order['stopLoss']
    #                 #response_text += f"Stop Loss: {stop_loss_info['type']} @ {stop_loss_info['stopPrice']:.2f}\n"
    #                 if stop_loss_info['type'] == "trailing_stop":
    #                     response_text += f"Stop Loss: {stop_loss_info['type']} @ {stop_loss_info['trailAmount']:.2f}\n"
    #                 else:
    #                     response_text += f"Stop Loss: {stop_loss_info['type']} @ {stop_loss_info['stopPrice']:.2f}\n"
    #         else:
    #             response_text = f"Error sending {order['action']} order for {order['ticker']}: Unsuccessful response from server\n"
    #             response_text += f"Response: {json.dumps(response_data, indent=2)}\n\n"
            
    #         return response_text
    #     except requests.RequestException as e:
    #         return f"Error sending {order['action']} order for {order['ticker']}: {str(e)}\n\n"

   

 

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

            self.databento_worker = DatabentoWorker(key=self.databento_key, is_replay=self.is_replay_mode)
            self.databento_worker.add_subscription(
                subscription_id="main",
                dataset="GLBX.MDP3",
                schema="ohlcv-1s",
                stype_in="continuous",
                symbols=[symbol]
            )
            
            self.databento_worker.data_received.connect(self.handle_databento_data)
            self.databento_worker.symbol_mapped.connect(self.handle_symbol_mapping)
            self.databento_worker.connection_error.connect(self.handle_databento_error)
            self.databento_worker.start()
            
            self.is_databento_initialized = True
            self.update_response_area(f"Databento worker initialized for {current_ticker}. Starting to receive price updates.\n")
        except Exception as e:
            self.update_response_area(f"Error initializing Databento worker: {str(e)}\n")
            self.databento_worker = None
            self.is_databento_initialized = False

    def handle_databento_error(self, error_msg):
        self.update_response_area(f"{error_msg}\n")
        self.update_response_area("Attempting to reconnect in 30 seconds...\n")
        self.databento_reconnect_timer.start(30000)  # 30 seconds

    def stop_databento_worker(self):
        if self.databento_worker:
            self.databento_worker.stop()
            self.databento_worker.wait()
            self.databento_worker = None
        self.is_databento_initialized = False
        self.databento_reconnect_timer.stop()
        self.update_response_area("Databento connection stopped. Price updates disabled.\n")



    def initialize_historical_data(self, start_datetime, end_datetime):
        try:
            current_ticker = self.ticker_combo.currentText()
            symbol = self.symbol_map.get(current_ticker)
            
            if not symbol:
                raise ValueError(f"No symbol mapping found for ticker: {current_ticker}")

            client = db.Historical(self.databento_key)
            
            data = client.timeseries.get_range(
                dataset="GLBX.MDP3",
                symbols=[symbol],
                schema="ohlcv-1s",
                stype_in="continuous",
                start=start_datetime,
                end=end_datetime,
                limit=100  # Adjust this value as needed
            )
            
            self.historical_data = list(data)  # Convert iterator to list
            self.historical_data_index = 0
            self.update_response_area(f"Historical data loaded for {current_ticker} from {start_datetime} to {end_datetime}. {len(self.historical_data)} records loaded.\n")
            
            # Start the historical data playback
            self.start_historical_playback()
        except Exception as e:
            self.update_response_area(f"Error loading historical data: {str(e)}\n")


    def process_historical_data(self, data):
        for record in data:
            # Process each record similar to how you handle live data
            self.handle_databento_data("historical", record)
        
        self.update_response_area("Finished processing historical data.\n")
    
    def start_historical_playback(self):
        self.historical_timer = QTimer(self)
        self.historical_timer.timeout.connect(self.play_next_historical_data)
        self.historical_timer.start(1000)  # Update every 1000 ms (1 second)

    def play_next_historical_data(self):
        while self.historical_data_index < len(self.historical_data):
            record = self.historical_data[self.historical_data_index]
            self.historical_data_index += 1
            
            if not isinstance(record, db.SystemMsg):
                self.handle_databento_data("historical", record)
                break
        else:
            self.historical_timer.stop()
            self.update_response_area("Historical data playback completed.\n")


    def handle_symbol_mapping(self, subscription_id, message):
        if subscription_id == "main":
            instrument_id = message.instrument_id
            continuous_symbol = message.stype_in_symbol
            raw_symbol = message.stype_out_symbol
            self.instrument_id_map[instrument_id] = continuous_symbol
            print(f"Symbol Mapping: {continuous_symbol} ({raw_symbol}) has an instrument ID of {instrument_id}")

    
    def toggle_price_updates(self, state):
        if state:
            self.update_response_area("Initializing Databento connection...\n")
            self.initialize_databento_worker()
        else:
            self.update_response_area("Stopping Databento connection...\n")
            self.stop_databento_worker()

  
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

    def toggle_replay_mode(self, checked):
        self.is_replay_mode = checked
        if checked:
            self.update_response_area("Historical data mode activated. Please configure settings.\n")
            self.configure_replay_settings()
        else:
            self.update_response_area("Historical data mode deactivated. Switching to live data.\n")
            if hasattr(self, 'historical_timer'):
                self.historical_timer.stop()
            if self.is_databento_initialized:
                self.initialize_databento_worker()
 
    def configure_replay_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Historical Data Settings")
        layout = QFormLayout(dialog)

        start_date = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        start_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        layout.addRow("Start Date:", start_date)

        end_date = QDateTimeEdit(QDateTime.currentDateTime())
        end_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        layout.addRow("End Date:", end_date)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_() == QDialog.Accepted:
            start_datetime = start_date.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
            end_datetime = end_date.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
            self.initialize_historical_data(start_datetime, end_datetime)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TradingApp()
    ex.show()
    # Ensure cleanup happens before the app exits
    #app.aboutToQuit.connect(ex.cleanup)
    sys.exit(app.exec_())