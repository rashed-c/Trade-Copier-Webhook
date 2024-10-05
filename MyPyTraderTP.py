import sys
import json
import requests
import os
import math 
from datetime import datetime, timezone, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, 
                             QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QSpinBox, QSizePolicy,
                             QCheckBox, QTableWidget, QTableWidgetItem, QScrollArea, QMenuBar, QAction)
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon, QPixmap
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer, QThread, pyqtSignal, QMetaObject, pyqtSlot
import databento as db
import pandas as pd 
import time
import sip


from dataclasses import dataclass

@dataclass
class TPInfo:
    quantity: int
    target: float
    price: float = 0.0

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

class TPFieldWidget(QWidget):
    removed = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, quantity=1, target=0, parent=None):
        super().__init__(parent)
        self.setup_ui(quantity, target)

    def setup_ui(self, quantity, target):
        layout = QHBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Qty:"))
        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setValue(quantity)
        self.quantity_input.setFixedWidth(50)
        layout.addWidget(self.quantity_input)

        layout.addWidget(QLabel("Target:"))
        self.target_input = QLineEdit(str(target))
        self.target_input.setFixedWidth(60)
        layout.addWidget(self.target_input)

        self.target_price_label = QLabel(f"@ {target}")
        self.target_price_label.setStyleSheet("color: gray;")
        layout.addWidget(self.target_price_label)

        remove_button = QPushButton("Remove")
        remove_button.setFixedWidth(70)
        remove_button.clicked.connect(self.remove_clicked)
        layout.addWidget(remove_button)

        layout.addStretch(1)

        self.quantity_input.valueChanged.connect(self.on_change)
        self.target_input.textChanged.connect(self.on_change)

    def remove_clicked(self):
        self.removed.emit(self)

    def on_change(self):
        self.changed.emit()

    def get_values(self):
        return self.quantity_input.value(), float(self.target_input.text())

    def update_target_price(self, price):
        try:
            target = float(self.target_input.text())
            self.target_price_label.setText(f"@ {price:.2f}")
        except ValueError:
            self.target_price_label.setText("@ Invalid input")


class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Trading App")
        self.setGeometry(100, 100, 400, 650)
        
        self.load_settings()

        self.tp_infos = []
        self.active_orders = {}
        self.entry_price = None
        self.orders_file = 'active_orders.json'
        

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
        
        self.setup_ui()
        
        self.instrument_id_map = {}
        self.current_prices = {ticker: 0 for ticker in self.symbol_map}
        
        self.initialize_price_and_stoploss()
        self.populate_tp_fields_from_active_orders()

        self.databento_key = "db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL"

        self.update_trade_status()
        self.setup_menu_bar()

        self.update_checkbox.setChecked(True)
        self.always_on_top_checkbox.setChecked(True)
        self.load_active_orders()
        self.check_and_execute_tps_on_startup()
        


    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
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
        
        # Add "Always on Top" checkbox
        self.always_on_top_checkbox = QCheckBox("Always on Top")
        self.always_on_top_checkbox.stateChanged.connect(self.toggle_always_on_top)
      
      

        # Add Trade Management Buttons
        trade_management_layout = QHBoxLayout()
        self.clear_trade_button = QPushButton("Clear Trade")
        self.clear_trade_button.clicked.connect(self.clear_trade)
        trade_management_layout.addWidget(self.clear_trade_button)
        
        self.add_trade_button = QPushButton("Add/Update Trade")
        self.add_trade_button.clicked.connect(self.add_or_update_trade)
        trade_management_layout.addWidget(self.add_trade_button)
        
        main_layout.addLayout(trade_management_layout)

        # TP section
        tp_layout = QVBoxLayout()
        tp_header_layout = QHBoxLayout()
        tp_header_layout.addWidget(QLabel("Take Profits:"))
        self.save_tp_button = QPushButton("Save TP")
        self.save_tp_button.clicked.connect(self.save_tp_changes)
        self.save_tp_button.setEnabled(False)
        tp_header_layout.addWidget(self.save_tp_button)
        self.add_tp_button = QPushButton("Add TP")
        self.add_tp_button.clicked.connect(self.add_tp_field)
        tp_header_layout.addWidget(self.add_tp_button)
        tp_layout.addLayout(tp_header_layout)

        self.tp_scroll_area = QScrollArea()
        self.tp_scroll_area.setWidgetResizable(True)
        self.tp_widget = QWidget()
        self.tp_layout = QVBoxLayout(self.tp_widget)
        self.tp_scroll_area.setWidget(self.tp_widget)
        tp_layout.addWidget(self.tp_scroll_area)

        main_layout.addLayout(tp_layout)
        
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

        #Timer 

        # self.tp_update_timer = QTimer()
        # self.tp_update_timer.setSingleShot(True)
        # self.tp_update_timer.timeout.connect(self.update_all_tp_amounts)
        #self.timer = QTimer(self)

       


        # Set size policy for the central widget to be expanding
        central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


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
        with open(self.orders_file, 'w') as f:
            json.dump(self.active_orders, f, indent=2)

    def load_active_orders(self):
        if os.path.exists(self.orders_file):
            with open(self.orders_file, 'r') as f:
                self.active_orders = json.load(f)
            
            # Restart monitoring for all loaded orders
            for order_id in self.active_orders:
                self.monitor_tp_levels(order_id)



    def clear_trade(self):
        self.active_orders.clear()
        self.entry_price = None
        self.clear_tp_fields()
        self.update_trade_status()
        self.save_active_orders()
        self.update_response_area("Trade cleared. All TPs removed.\n")

    def add_or_update_trade(self):
        current_price = float(self.price_input.text())
        current_entry_price = self.entry_price if self.active_orders else None
        dialog = AddTradeDialog(self, current_price, current_entry_price)
        if dialog.exec_():
            entry_price, action = dialog.get_trade_info()
            self.entry_price = entry_price
            
            if self.active_orders:
                # Update existing trade
                order_id = list(self.active_orders.keys())[0]
                self.active_orders[order_id]['entry_price'] = entry_price
                self.active_orders[order_id]['action'] = action
                self.update_response_area(f"Trade updated. New entry price: {entry_price}, Action: {action}\n")
            else:
                # Add new trade
                order_id = f"manual_order_{int(time.time())}"
                self.active_orders[order_id] = {
                    "symbol": self.ticker_combo.currentText(),
                    "action": action,
                    "quantity": self.quantity_input.value(),
                    "entry_price": entry_price,
                    "take_profits": [],
                    "timestamp": int(time.time())
                }
                self.update_response_area(f"New trade added. Entry price: {entry_price}, Action: {action}\n")
            
            self.save_active_orders()
            self.update_trade_status()
            self.update_all_tp_amounts()
            
            # Check and potentially execute TPs immediately
            self.check_and_execute_tps(order_id, current_price)


    def check_and_execute_tps_on_startup(self):
        for order_id, order in list(self.active_orders.items()):
            symbol = order["symbol"]
            action = order["action"]
            entry_price = order["entry_price"]
            current_price = self.current_prices.get(symbol, entry_price)

            tps_to_remove = []
            for tp in order["take_profits"]:
                tp_quantity = tp["quantity"]
                tp_target = tp["target"]
                tp_price = entry_price + tp_target if action == "buy" else entry_price - tp_target
                
                if (action == "buy" and current_price >= tp_price) or \
                (action == "sell" and current_price <= tp_price):
                    if self.submit_tp_exit_order(order_id, tp_quantity, current_price):
                        tps_to_remove.append(tp)
                        order["quantity"] -= tp_quantity

            # Remove executed TPs
            for tp in tps_to_remove:
                order["take_profits"].remove(tp)

            if not order["take_profits"] or order["quantity"] <= 0:
                if order["quantity"] <= 0:
                    del self.active_orders[order_id]

        self.save_active_orders()
        self.update_trade_status()
        self.update_tp_ui()

    def check_and_execute_tps(self, order_id, current_price):
        order = self.active_orders[order_id]
        action = order['action']
        entry_price = order['entry_price']
        executed_tps = []
        remaining_tps = []

        for tp in order['take_profits']:
            quantity = tp['quantity']
            tp_price = tp['target']

            if (action == 'buy' and current_price >= tp_price) or (action == 'sell' and current_price <= tp_price):
                # TP condition met, execute the order
                self.execute_tp_order(order_id, quantity, tp_price)
                executed_tps.append((quantity, tp_price))
            else:
                remaining_tps.append(tp)

        # Update the order's take_profits
        order['take_profits'] = remaining_tps
        self.save_active_orders()

        # Update TP fields
        self.update_all_tp_amounts()

        # Provide feedback
        if executed_tps:
            executed_msg = ", ".join([f"{qty} @ {price:.2f}" for qty, price in executed_tps])
            self.update_response_area(f"Take Profits executed: {executed_msg}\n")

    def execute_tp_order(self, order_id, quantity, tp_price):
        order = self.active_orders[order_id]
        symbol = order['symbol']
        
        exit_order = {
            "ticker": symbol,
            "action": "exit",
            "orderType": "market",  # Changed to market order for immediate execution
            "quantity": quantity,
            "relatedOrderId": order_id
        }
        
        try:
            response = requests.post(self.api_url, json=exit_order)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get("success"):
                self.update_response_area(f"Take Profit exit order executed: {quantity} shares at approximately {tp_price:.2f}\n")
                
                # Update the active order
                order["quantity"] -= quantity
                if order["quantity"] <= 0:
                    del self.active_orders[order_id]
                    self.update_response_area(f"Order {order_id} fully closed and removed from active orders.\n")
                
                self.save_active_orders()
                self.update_trade_status()
            else:
                self.update_response_area(f"Error executing TP exit order: {response_data}\n")
        except requests.RequestException as e:
            self.update_response_area(f"Error executing TP exit order: {str(e)}\n")


    def update_tp_ui(self):
        # Clear existing widgets in tp_layout
        for i in reversed(range(self.tp_layout.count())): 
            widget = self.tp_layout.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)

        # Add widgets for each TPInfo
        for index in range(len(self.tp_infos)):
            self.update_single_tp_ui(index)

        self.adjust_scroll_area_height() 

        # Add widgets for each TPInfo
        for index, tp_info in enumerate(self.tp_infos):
            tp_widget = QWidget()
            tp_layout = QHBoxLayout(tp_widget)

            quantity_input = QSpinBox()
            quantity_input.setMinimum(1)
            quantity_input.setValue(tp_info.quantity)
            quantity_input.valueChanged.connect(lambda v, i=index: self.update_tp_info(i, quantity=v))
            tp_layout.addWidget(QLabel("Qty:"))
            tp_layout.addWidget(quantity_input)

            target_input = QLineEdit(str(tp_info.target))
            target_input.textChanged.connect(lambda t, i=index: self.update_tp_info(i, target=float(t) if t else 0))
            tp_layout.addWidget(QLabel("Target:"))
            tp_layout.addWidget(target_input)

            remove_button = QPushButton("Remove")
            remove_button.clicked.connect(lambda _, i=index: self.remove_tp_field(i))
            tp_layout.addWidget(remove_button)

            self.tp_layout.addWidget(tp_widget)

        self.adjust_scroll_area_height()


    def update_all_tp_targets(self):
        for tp_field in self.tp_fields:
            self.update_tp_target(tp_field)



    def add_tp_field(self, quantity=1, target=0):
        tp_info = TPInfo(quantity, target)
        self.tp_infos.append(tp_info)
        self.update_single_tp_ui(len(self.tp_infos) - 1)
        self.save_tp_button.setEnabled(True)
        self.adjust_scroll_area_height()


    def update_single_tp_ui(self, index):
        tp_info = self.tp_infos[index]
        tp_widget = QWidget()
        tp_layout = QHBoxLayout(tp_widget)

        quantity_input = QSpinBox()
        quantity_input.setMinimum(1)
        quantity_input.setValue(tp_info.quantity)
        quantity_input.valueChanged.connect(lambda v, i=index: self.update_tp_info(i, quantity=v))
        tp_layout.addWidget(QLabel("Qty:"))
        tp_layout.addWidget(quantity_input)

        offset_input = QLineEdit(str(tp_info.offset))
        offset_input.textChanged.connect(lambda t, i=index: self.update_tp_info(i, offset=float(t) if t else 0))
        tp_layout.addWidget(QLabel("Offset:"))
        tp_layout.addWidget(offset_input)

        target_price_label = QLabel(f"Target: {tp_info.target_price:.2f}")
        tp_layout.addWidget(target_price_label)

        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(lambda _, i=index: self.remove_tp_field(i))
        tp_layout.addWidget(remove_button)

        self.tp_layout.addWidget(tp_widget)
            
    
    # def add_tp_field(self, quantity=1, target=0):
    #     new_tp_widget = QWidget()
    #     tp_layout = QHBoxLayout(new_tp_widget)

    #     quantity_input = QSpinBox()
    #     quantity_input.setMinimum(1)
    #     quantity_input.setValue(quantity)
    #     quantity_input.valueChanged.connect(lambda v: self.on_tp_changed())
    #     tp_layout.addWidget(QLabel("Qty:"))
    #     tp_layout.addWidget(quantity_input)

    #     target_input = QLineEdit(str(target))
    #     target_input.textChanged.connect(lambda t: self.on_tp_changed())
    #     tp_layout.addWidget(QLabel("Target:"))
    #     tp_layout.addWidget(target_input)

    #     remove_button = QPushButton("Remove")
    #     remove_button.clicked.connect(lambda: self.remove_tp_field(new_tp_widget))
    #     tp_layout.addWidget(remove_button)

    #     self.tp_layout.addWidget(new_tp_widget)
    #     self.adjust_scroll_area_height()
    #     self.save_tp_button.setEnabled(True)

    
    # def add_tp_field(self, quantity=1, target=0):
    #     self.tp_infos.append(TPInfo(quantity, target))
    #     self.update_tp_ui()

    
    # def add_tp_field(self, quantity=1, target=0):
    #     self.tp_infos.append(TPInfo(quantity, target))
    #     self.update_tp_ui()
    #     self.save_tp_button.setEnabled(True)


    # def add_tp_fields(self, quantity=1, tp_target=0):
    #     tp_field = TPFieldWidget(quantity, tp_target)
    #     tp_field.removed.connect(self.remove_tp_fields)
    #     tp_field.changed.connect(self.on_tp_changed)
    #     self.tp_layout.addWidget(tp_field)
    #     self.tp_fields.append(tp_field)
    #     self.update_tp_target(tp_field)

    def update_single_tp_ui(self, index):
        tp_info = self.tp_infos[index]
        tp_widget = QWidget()
        tp_layout = QHBoxLayout(tp_widget)

        quantity_input = QSpinBox()
        quantity_input.setMinimum(1)
        quantity_input.setValue(tp_info.quantity)
        quantity_input.valueChanged.connect(lambda v, i=index: self.update_tp_info(i, quantity=v))
        tp_layout.addWidget(QLabel("Qty:"))
        tp_layout.addWidget(quantity_input)

        target_input = QLineEdit(str(tp_info.target))
        target_input.textChanged.connect(lambda t, i=index: self.update_tp_info(i, target=float(t) if t else 0))
        tp_layout.addWidget(QLabel("Target:"))
        tp_layout.addWidget(target_input)

        price_label = QLabel(f"Price: {tp_info.price:.2f}")
        tp_layout.addWidget(price_label)

        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(lambda _, i=index: self.remove_tp_field(i))
        tp_layout.addWidget(remove_button)

        self.tp_layout.addWidget(tp_widget)


    def update_tp_info(self, index, quantity=None, target=None):
        if 0 <= index < len(self.tp_infos):
            if quantity is not None:
                self.tp_infos[index].quantity = quantity
            if target is not None:
                self.tp_infos[index].target = target
            self.update_all_tp_amounts()
        self.save_tp_button.setEnabled(True)


    def remove_tp_field(self, index):
        if 0 <= index < len(self.tp_infos):
            del self.tp_infos[index]
            self.update_tp_ui()
        self.save_tp_button.setEnabled(True)
        self.adjust_scroll_area_height()


    def clear_tp_fields(self):
        self.tp_infos.clear()
        self.update_tp_ui()

    def update_tp_target(self, tp_field):
        if self.active_orders:
            latest_order = list(self.active_orders.values())[-1]
            action = latest_order['action']
            entry_price = latest_order['entry_price']
            quantity, tp_target = tp_field.get_values()
            target_price = entry_price + tp_target if action == 'buy' else entry_price - tp_target
            tp_field.update_target_price(target_price)
        else:
            tp_field.update_target_price(0)

    @pyqtSlot() 
    def update_all_tp_amounts(self):
        try:
            if self.active_orders:
                latest_order = list(self.active_orders.values())[-1]
                action = latest_order['action']
                entry_price = latest_order['entry_price']
                current_price = float(self.price_input.text())

                for tp_info in self.tp_infos:
                    if action == 'buy':
                        tp_info.price = entry_price + tp_info.target
                    else:
                        tp_info.price = entry_price - tp_info.target

            self.update_tp_ui()
        except Exception as e:
            print(f"Error in update_all_tp_amounts: {type(e).__name__}: {str(e)}")




    # @pyqtSlot()
    # def update_all_tp_amounts(self):
    #     try:
    #         current_tp_data = [(tp.quantity, tp.target) for tp in self.tp_infos]
    #         self.clear_tp_fields()
    #         for quantity, target in current_tp_data:
    #             self.add_tp_field(quantity, target)
    #         self.update_tp_ui()
    #         self.adjust_scroll_area_height()
    #     except Exception as e:
    #         print(f"Error in update_all_tp_amounts: {type(e).__name__}: {str(e)}")

    # def on_tp_changed(self):
    #     self.save_tp_button.setEnabled(True)




    def save_tp_changes(self):
        if not self.active_orders:
            self.update_response_area("No active orders to update TP levels.\n")
            return

        latest_order_id = list(self.active_orders.keys())[-1]
        latest_order = self.active_orders[latest_order_id]
        
        new_take_profits = []
        for tp_info in self.tp_infos:
            new_take_profits.append({
                "quantity": tp_info.quantity,
                "target": tp_info.target,
                "price": tp_info.price
            })

        latest_order['take_profits'] = new_take_profits
        self.save_active_orders()
        self.update_response_area(f"Take Profit levels updated for order {latest_order_id}\n")
        self.save_tp_button.setEnabled(False)
        self.update_all_tp_amounts()


    # @pyqtSlot()
    # def update_all_tp_amounts(self):
    #     try:
    #         # Store current TP data
    #         current_tp_data = []
    #         for tp in self.tp_fields:
    #             if not sip.isdeleted(tp['quantity']) and not sip.isdeleted(tp['target']):
    #                 quantity = tp['quantity'].value()
    #                 target_text = tp['target'].text().strip()
    #                 if target_text:
    #                     try:
    #                         target = float(target_text)
    #                         current_tp_data.append((quantity, target))
    #                     except ValueError:
    #                         print(f"Skipping invalid TP target: {target_text}")
    #             else:
    #                 print("Skipping deleted TP field")
            
    #         # Clear all existing TP fields
    #         self.clear_tp_fields()
            
    #         # Rebuild TP fields
    #         for quantity, target in current_tp_data:
    #             self.add_tp_fields(quantity, target)
            
    #         # Update the TP targets
    #         for tp_field in self.tp_fields:
    #             self.update_tp_target(tp_field)
            
    #         self.adjust_scroll_area_height()
    #     except Exception as e:
    #         print(f"Error in update_all_tp_amounts: {type(e).__name__}: {str(e)}")


    # @pyqtSlot()
    # def update_all_tp_amounts(self):
    #     try:
    #         # Store current TP data
    #         current_tp_data = []
    #         for tp in self.tp_fields:
    #             quantity = tp['quantity'].value()
    #             target_text = tp['target'].text().strip()
    #             if target_text:
    #                 try:
    #                     target = float(target_text)
    #                     current_tp_data.append((quantity, target))
    #                 except ValueError:
    #                     print(f"Skipping invalid TP target: {target_text}")
    #             else:
    #                 print("Skipping empty TP target")
            
    #         # Clear all existing TP fields
    #         self.clear_tp_fields()
            
    #         # Rebuild TP fields
    #         for quantity, target in current_tp_data:
    #             self.add_tp_fields(quantity, target)
            
    #         # Update the TP targets
    #         for tp_field in self.tp_fields:
    #             self.update_tp_target(tp_field)
            
    #         self.adjust_scroll_area_height()
    #     except Exception as e:
    #         print(f"Error in update_all_tp_amounts: {type(e).__name__}: {str(e)}")



    def monitor_tp_levels(self, order_id):
        timer = QTimer(self)
        if order_id not in self.active_orders:
            return  # Order no longer active, don't monitor

        order = self.active_orders[order_id]
        symbol = order["symbol"]
        action = order["action"]
        entry_price = order["entry_price"]
        
        def check_tp_levels():
            if order_id not in self.active_orders:
                timer.stop()  # Stop monitoring if order is no longer active
                return

            current_price = self.current_prices.get(symbol, entry_price)
            tps_to_remove = []
            for tp in order["take_profits"]:
                tp_quantity = tp["quantity"]
                tp_target = tp["target"]
                tp_price = entry_price + tp_target if action == "buy" else entry_price - tp_target
                
                if (action == "buy" and current_price >= tp_price) or \
                (action == "sell" and current_price <= tp_price):
                    self.submit_tp_exit_order(order_id, tp_quantity, current_price)
                    tps_to_remove.append(tp)
                    order["quantity"] -= tp_quantity
            
            # Remove executed TPs
            for tp in tps_to_remove:
                order["take_profits"].remove(tp)
            
            if not order["take_profits"] or order["quantity"] <= 0:
                # All TPs hit or no quantity left, stop monitoring
                timer.stop()
                if order["quantity"] <= 0:
                    del self.active_orders[order_id]
                    self.save_active_orders()
                    self.update_trade_status()
                    self.update_tp_ui()
            
            # Update UI
            self.update_all_tp_amounts()
        
        # Check TP levels immediately upon starting to monitor
        check_tp_levels()
        
        timer = QTimer(self)
        timer.timeout.connect(check_tp_levels)
        timer.start(1000)  # Check every second


    

    def on_tp_edit_finished(self):
        self.save_tp_button.setEnabled(True)
        self.update_all_tp_amounts()



    def adjust_scroll_area_height(self):
        total_height = self.tp_layout.sizeHint().height()
        max_height = 200
        min_height = 100
        new_height = max(min(total_height, max_height), min_height)
        self.tp_scroll_area.setFixedHeight(new_height)
    

    

    # def on_tp_changed(self, tp_field):
    #     self.save_tp_button.setEnabled(True)
    #     self.tp_update_timer.start(500)  # Wait for 500 ms before updating


    # def remove_tp_fields(self, widget):
    #     self.tp_layout.removeWidget(widget)
    #     self.tp_fields = [tp for tp in self.tp_fields if tp['widget'] != widget]
    #     widget.deleteLater()
    #     QApplication.processEvents()  # Process the deleteLater event immediately
    #     self.save_tp_button.setEnabled(True)  # Enable the save button when a TP is removed
    #     self.update_all_tp_amounts()  # Update remaining TP fields
    #     self.adjust_scroll_area_height()  # Adjust scroll area height after removal


   # def add_tp_fields(self, quantity=1, tp_target=0):
    #     tp_field_widget = QWidget()
    #     tp_field_layout = QHBoxLayout(tp_field_widget)
    #     tp_field_layout.setSpacing(5)
    #     tp_field_layout.setContentsMargins(0, 0, 0, 0)
        
    #     quantity_input = QSpinBox()
    #     quantity_input.setMinimum(1)
    #     quantity_input.setValue(quantity)
    #     quantity_input.setFixedWidth(50)
    #     tp_field_layout.addWidget(QLabel("Qty:"))
    #     tp_field_layout.addWidget(quantity_input)
        
    #     tp_target_input = QLineEdit(str(tp_target))
    #     tp_target_input.setFixedWidth(60)
    #     tp_field_layout.addWidget(QLabel("Target:"))
    #     tp_field_layout.addWidget(tp_target_input)
        
    #     target_price_label = QLabel(f"@ {tp_target}")
    #     target_price_label.setStyleSheet("color: gray;")
    #     tp_field_layout.addWidget(target_price_label)
        
    #     remove_button = QPushButton("Remove")
    #     remove_button.setFixedWidth(70)
    #     remove_button.clicked.connect(lambda: self.remove_tp_fields(tp_field_widget))
    #     tp_field_layout.addWidget(remove_button)
        
    #     tp_field_layout.addStretch(1)
    #     self.tp_layout.addWidget(tp_field_widget)
    
    #     tp_field = {
    #         'widget': tp_field_widget,
    #         'quantity': quantity_input,
    #         'target': tp_target_input,
    #         'label': target_price_label,
    #     }
    #     self.tp_fields.append(tp_field)
        
    #     # Connect signals
    #     quantity_input.valueChanged.connect(lambda: self.on_tp_changed(tp_field))
    #     tp_target_input.textChanged.connect(lambda: self.on_tp_changed(tp_field))
        
    #     self.update_tp_target(tp_field) 


    # def save_tp_changes(self):
    #     if not self.active_orders:
    #         self.update_response_area("No active orders to update TP levels.\n")
    #         return

    #     latest_order_id = list(self.active_orders.keys())[-1]
    #     latest_order = self.active_orders[latest_order_id]
        
    #     new_take_profits = []
    #     for tp_field in self.tp_fields:
    #         quantity = tp_field['quantity'].value()
    #         tp_target = float(tp_field['target'].text())
    #         tp_price = latest_order['entry_price'] + tp_target if latest_order['action'] == 'buy' else latest_order['entry_price'] - tp_target
    #         new_take_profits.append({
    #             "quantity": quantity,
    #             "target": tp_price,
    #             "offset": tp_target
    #         })
    #         # Update original values
    #         tp_field['original_quantity'] = quantity
    #         tp_field['original_target'] = tp_target

    #     latest_order['take_profits'] = new_take_profits
    #     self.save_active_orders()
    #     self.update_response_area(f"Take Profit levels updated for order {latest_order_id}\n")
    #     self.save_tp_button.setEnabled(False)


    # def clear_tp_fields(self):
    #     while self.tp_layout.count():
    #         item = self.tp_layout.takeAt(0)
    #         if item.widget():
    #             item.widget().setParent(None)
    #             item.widget().deleteLater()
    #     self.tp_fields.clear()
    #     QApplication.processEvents()

    # def update_tp_target(self, tp_field):
    #     try:
    #         quantity = tp_field['quantity'].value()
    #         tp_target_text = tp_field['target'].text().strip()
            
    #         if not tp_target_text:
    #             tp_field['label'].setText("@ Enter target")
    #             return

    #         tp_target = float(tp_target_text)
            
    #         if self.active_orders:
    #             latest_order = list(self.active_orders.values())[-1]
    #             action = latest_order['action']
    #             entry_price = latest_order['entry_price']
    #             target_price = entry_price + tp_target if action == 'buy' else entry_price - tp_target
    #             tp_field['label'].setText(f"@ {target_price:.2f}")
    #         else:
    #             tp_field['label'].setText("@ N/A (No active trade)")
        
    #     except ValueError:
    #         tp_field['label'].setText("@ Invalid input")
    #     except Exception as e:
    #         print(f"Error updating TP target: {type(e).__name__}: {str(e)}")
    #         tp_field['label'].setText("@ Error")


    def update_active_tp_level(self, quantity, tp_target, target_price):
        if not self.active_orders:
            return

        latest_order_id = list(self.active_orders.keys())[-1]
        latest_order = self.active_orders[latest_order_id]
        
        # Find matching TP level or add new one
        matching_tp = next((tp for tp in latest_order['take_profits'] if tp['quantity'] == quantity), None)
        
        if matching_tp:
            matching_tp['offset'] = tp_target
            matching_tp['target'] = target_price
        else:
            latest_order['take_profits'].append({
                'quantity': quantity,
                'offset': tp_target,
                'target': target_price
            })
        
        # Update local state
        self.save_active_orders()
        self.update_response_area(f"Take Profit levels updated for order {latest_order_id}\n")

    def populate_tp_fields_from_active_orders(self):
        if not self.active_orders:
            return

        self.tp_infos.clear()  # Clear existing TP infos

        # Get the most recent active order
        recent_order = max(self.active_orders.values(), key=lambda x: x.get('timestamp', 0))
        
        for tp in recent_order['take_profits']:
            self.tp_infos.append(TPInfo(tp['quantity'], tp['target']))
        
        self.update_tp_ui()




    def update_trade_status(self):
        if self.active_orders:
            latest_order = list(self.active_orders.values())[-1]
            entry_price = latest_order['entry_price']
            position_type = "Long" if latest_order['action'] == 'buy' else "Short"
            status_text = f"Status: In trade @ {entry_price:.2f} ({position_type})"
            self.trade_status_label.setText(status_text)
            self.trade_status_label.setStyleSheet("color: green;")
            self.save_tp_button.setEnabled(True)
        else:
            self.trade_status_label.setText("Status: Not in trade")
            self.trade_status_label.setStyleSheet("color: red;")
            self.save_tp_button.setEnabled(False)


 
    def update_entry_prices(self):
        current_price = float(self.price_input.text())
        for tp_field in self.tp_fields:
            self.update_tp_target(tp_field)



    ##-------------TP functions----------------

    def toggle_always_on_top(self, state):
        if state == Qt.Checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            self.update_response_area("Window set to always on top.\n")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()
            self.update_response_area("Window no longer always on top.\n")

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

    def open_settings(self):
        dialog = SettingsDialog(self, self.api_url, self.databento_key)
        if dialog.exec_() == QDialog.Accepted:
            self.api_url, self.databento_key = dialog.get_settings()
            self.save_settings()
            self.update_response_area(f"Settings updated:\nWebhook URL: {self.api_url}\nDatabento API Key: {'*' * len(self.databento_key)}\n")
            self.initialize_databento_client()

    def initialize_price_and_stoploss(self):
        initial_ticker = self.ticker_combo.currentText()
        self.update_default_values(initial_ticker)

    def update_default_values(self, ticker):
        default_stop_loss = self.default_stop_loss_amounts.get(ticker, 0)
        self.stop_loss_input.setText(str(default_stop_loss))


    def on_stop_loss_type_changed(self, stop_loss_type):
        self.trail_amount_input.setEnabled(stop_loss_type == "Trailing")

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
                    self.entry_price = current_price
                    order_id = response_data.get('id', f"order_{int(time.time())}")
                    self.active_orders[order_id] = {
                        "symbol": symbol,
                        "action": action,
                        "quantity": quantity,
                        "entry_price": self.entry_price,
                        "take_profits": [{"quantity": tp.quantity, "target": tp.target, "price": tp.price} for tp in self.tp_infos],
                        "timestamp": int(time.time())
                    }
                    self.monitor_tp_levels(order_id)  # Start monitoring TPs for the new order
                    self.save_active_orders()
                    self.update_tp_ui()
                
                response_text = f"{action.capitalize()} order sent successfully for {symbol}!\n"
                if action != "exit":
                    response_text += f"Entry Price: {self.entry_price}\n"
                if "stopLoss" in order:
                    response_text += f"Stop Loss: {order['stopLoss']['type']} @ {order['stopLoss'].get('stopPrice', order['stopLoss'].get('trailAmount')):.2f}\n"
                
                if action == "exit":
                    # Remove the exited order from active_orders if it exists
                    exited_order_id = next((order_id for order_id, order in self.active_orders.items() if order["symbol"] == symbol), None)
                    if exited_order_id:
                        del self.active_orders[exited_order_id]
                        self.save_active_orders()
                        response_text += f"Removed order {exited_order_id} from active orders.\n"
                
                self.update_trade_status()  # Update trade status after order changes
            else:
                response_text = f"Error sending {action} order for {symbol}: Unsuccessful response from server\n"
                response_text += f"Response: {json.dumps(response_data, indent=2)}\n\n"
            
            self.update_response_area(response_text)
        except requests.RequestException as e:
            error_text = f"Error sending {action} order for {symbol}: {str(e)}\n\n"
            self.update_response_area(error_text)


    def submit_tp_exit_order(self, original_order_id, quantity, current_price):
        if original_order_id not in self.active_orders:
            self.update_response_area(f"Error: Order {original_order_id} not found in active orders.\n")
            return

        original_order = self.active_orders[original_order_id]
        symbol = original_order["symbol"]
        
        exit_order = {
            "ticker": symbol,
            "action": "exit",
            "orderType": "market",
            "quantity": quantity,
            "relatedOrderId": original_order_id
        }
        
        try:
            response = requests.post(self.api_url, json=exit_order)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get("success"):
                self.update_response_area(f"Take Profit exit order executed: {quantity} shares at approximately {current_price:.2f}\n")
                
                # Update the active order
                original_order["quantity"] -= quantity
                if original_order["quantity"] <= 0:
                    del self.active_orders[original_order_id]
                    self.update_response_area(f"Order {original_order_id} fully closed and removed from active orders.\n")
                
                self.save_active_orders()
                self.update_trade_status()
                self.update_tp_ui()
                return True
            else:
                self.update_response_area(f"Error executing TP exit order: {response_data}\n")
                return False
        except requests.RequestException as e:
            self.update_response_area(f"Error executing TP exit order: {str(e)}\n")
            return False


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
            symbol = self.symbol_map[current_ticker]
            
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
            # self.update_response_area(f"Databento worker initialized for {current_ticker}. Starting to receive price updates.\n")
        except Exception as e:
            self.update_response_area(f"Error initializing Databento worker: {str(e)}\n")
            self.databento_worker = None
            self.is_databento_initialized = False

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
                                QMetaObject.invokeMethod(self, "update_all_tp_amounts", Qt.QueuedConnection)
            except Exception as e:
                print(f"Error processing data: {type(e).__name__}: {str(e)}")

    def handle_symbol_mapping(self, subscription_id, message):
        if subscription_id == "main":
            instrument_id = message.instrument_id
            continuous_symbol = message.stype_in_symbol
            raw_symbol = message.stype_out_symbol
            self.instrument_id_map[instrument_id] = continuous_symbol
            print(f"Symbol Mapping: {continuous_symbol} ({raw_symbol}) has an instrument ID of {instrument_id}")



    def on_ticker_changed(self, ticker):
        price = self.current_prices.get(ticker, 0)
        self.price_input.setText(str(price))
        self.update_default_values(ticker)
        if self.is_databento_initialized:
            self.initialize_databento_worker()
        self.update_entry_prices()
        self.check_and_execute_tps_on_startup()  # Check TPs when ticker changes



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



if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TradingApp()
    ex.show()
    sys.exit(app.exec_())