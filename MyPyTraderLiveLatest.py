import sys
import json
import requests
import os
import math 
from datetime import datetime, timezone, timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, 
                             QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QSpinBox, QSizePolicy,
                             QCheckBox, QTableWidget, QTableWidgetItem)
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon, QPixmap
from PyQt5.QtCore import Qt, QSize, QPoint, QTimer, QThread, pyqtSignal
import databento as db
import pandas as pd 

def create_gear_icon():
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    pen = QPen(Qt.black, 2)
    painter.setPen(pen)
    
    center = pixmap.rect().center()
    outer_radius = 9
    inner_radius = 6
    num_teeth = 8
    
    for i in range(num_teeth * 2):
        angle = i * 2 * math.pi / (num_teeth * 2)
        radius = outer_radius if i % 2 == 0 else inner_radius
        x = center.x() + radius * math.cos(angle)
        y = center.y() + radius * math.sin(angle)
        painter.drawLine(center, QPoint(int(x), int(y)))
    
    painter.drawEllipse(center, 3, 3)
    painter.end()
    
    return QIcon(pixmap)

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

class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Trading App")
        self.setGeometry(100, 100, 400, 650)
        
        self.load_settings()
        
        self.databento_worker = None
        self.is_databento_initialized = False
        
        self.symbol_map = {
            "MES": "MES.c.0", 
            "MNQ": "MNQ.c.0",
            "MGC": "MGC.c.0",
            #"MES": "MES.c.0"
        }
        
        # self.default_trail_amounts = {
        #     "MES": 10,
        #     "MNQ": 30,
        #     "MGC": 4
        # }
        
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
        
        self.setup_ui()
        
        self.initialize_price_and_stoploss()

        self.databento_key = "db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL"

        #self.initialize_databento_worker()
        self.update_checkbox.setChecked(True)
        self.always_on_top_checkbox.setChecked(True)

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
        
        settings_layout = QHBoxLayout()
        settings_layout.addStretch()
        self.settings_button = QPushButton()
        self.settings_button.setIcon(create_gear_icon())
        self.settings_button.setFixedSize(QSize(30, 30))
        self.settings_button.clicked.connect(self.open_settings)
        settings_layout.addWidget(self.settings_button)
        main_layout.addLayout(settings_layout)
        
        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        main_layout.addWidget(self.response_area)
        
        for i in range(input_layout.rowCount()):
            input_layout.itemAtPosition(i, 0).widget().setFixedWidth(80)
        for i in range(stop_loss_layout.rowCount()):
            stop_loss_layout.itemAtPosition(i, 0).widget().setFixedWidth(80)
        
        # Add "Always on Top" checkbox
        self.always_on_top_checkbox = QCheckBox("Always on Top")
        self.always_on_top_checkbox.stateChanged.connect(self.toggle_always_on_top)
       # self.always_on_top_checkbox.setChecked(True)
        
        # Add the checkbox to the layout (adjust as needed based on your existing layout)
        settings_layout.addWidget(self.always_on_top_checkbox)

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

    # def on_ticker_changed(self, ticker):
    #     price = self.current_prices.get(ticker, 0)
    #     self.price_input.setText(str(price))
    #     self.update_default_values(ticker)
    #     if self.is_databento_initialized:
    #         self.initialize_databento_worker()

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
        
    # def send_order(self, action):
    #     ticker = self.ticker_combo.currentText()
    #     #symbol = self.symbol_map.get(ticker, ticker)
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
    #         "orderType": "limit",
    #         "limitPrice": current_price
    #     }
        
    #     if action != "exit":
    #         order["quantity"] = quantity
        
    #     if action in ["buy", "sell"]:
    #         stop_loss_type = self.stop_loss_type_combo.currentText()
    #         if stop_loss_type == "Trailing":
    #             try:
    #                 trail_amount = float(self.trail_amount_input.text())
    #                 order["stopLoss"] = {
    #                     "type": "trailing_stop",
    #                     "trailAmount": trail_amount
    #                 }
    #             except ValueError:
    #                 self.update_response_area("Error: Invalid input for trail amount.\n")
    #                 return
    #         elif stop_loss_amount != 0:
    #             # Calculate the actual stop loss price based on the action and current price
    #             if action == "buy":
    #                 stop_loss_price = current_price - stop_loss_amount
    #             else:  # sell
    #                 stop_loss_price = current_price + stop_loss_amount
                
    #             order["stopLoss"] = {
    #                 "type": self.get_stop_loss_type(stop_loss_type),
    #                 "stopPrice": stop_loss_price
    #             }
        
    #     try:
    #         response = requests.post(self.api_url, json=order)
    #         response.raise_for_status()
            
    #         response_data = response.json()
    #         if response_data.get("success"):
    #             response_text = f"{action.capitalize()} order sent successfully for {symbol}!\n"
    #             response_text += "Response:\n"
    #             response_text += f"  Order ID: {response_data.get('id', 'N/A')}\n"
    #             response_text += f"  Log ID: {response_data.get('logId', 'N/A')}\n"
                
    #             payload = response_data.get('payload', {})
    #             response_text += "  Details:\n"
    #             for key, value in payload.items():
    #                 response_text += f"    {key.capitalize()}: {value}\n"
                
    #             response_text += "\n"
    #         else:
    #             response_text = f"Error sending {action} order for {symbol}: Unsuccessful response from server\n"
    #             response_text += f"Response: {json.dumps(response_data, indent=2)}\n\n"
            
    #         self.update_response_area(response_text)
    #     except requests.RequestException as e:
    #         error_text = f"Error sending {action} order for {symbol}: {str(e)}\n\n"
    #         self.update_response_area(error_text)


    def send_order(self, action):
        ticker = self.ticker_combo.currentText()
       #symbol = self.symbol_map.get(ticker, ticker)
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
            "limitPrice": current_price
        }
        
        if action != "exit":
            order["quantity"] = quantity
        
        if action in ["buy", "sell"]:
            stop_loss_type = self.stop_loss_type_combo.currentText()
            if stop_loss_type == "Trailing":
                order["stopLoss"] = {
                    "type": "trailing_stop",
                    "trailAmount": stop_loss_amount
                }
            else:
                # Calculate the actual stop loss price based on the action and current price
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
                response_text = f"{action.capitalize()} order sent successfully for {symbol}!\n"
                response_text += "Response:\n"
                response_text += f"  Order ID: {response_data.get('id', 'N/A')}\n"
                response_text += f"  Log ID: {response_data.get('logId', 'N/A')}\n"
                
                payload = response_data.get('payload', {})
                response_text += "  Details:\n"
                for key, value in payload.items():
                    response_text += f"    {key.capitalize()}: {value}\n"
                
                response_text += "\n"
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

    def handle_symbol_mapping(self, subscription_id, message):
        if subscription_id == "main":
            instrument_id = message.instrument_id
            continuous_symbol = message.stype_in_symbol
            raw_symbol = message.stype_out_symbol
            self.instrument_id_map[instrument_id] = continuous_symbol
            # self.update_response_area(f"Symbol Mapping: {continuous_symbol} ({raw_symbol}) has an instrument ID of {instrument_id}\n")

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

                            # self.update_response_area(f"Updated {ticker} price: {close_price:.2f}\n")
                            
                            # if hasattr(message, 'open') and hasattr(message, 'high') and hasattr(message, 'low'):
                            #     open_price = message.open / scale_factor
                            #     high_price = message.high / scale_factor
                            #     low_price = message.low / scale_factor
                            #     self.update_response_area(f"OHLCV: Open: {open_price:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Close: {close_price:.2f}, Volume: {message.volume}\n")
                            
                            # if hasattr(message, 'ts_event'):
                            #     self.update_response_area(f"Timestamp: {message.ts_event}\n")
                        # else:
                        #     self.update_response_area(f"Received data for unmatched ticker: {ticker}\n")
                    # else:
                    #     self.update_response_area(f"Received data for unmatched instrument_id: {instrument_id}\n")
                # else:
                #     self.update_response_area("Received message without instrument_id attribute\n")
            except Exception as e:
                self.update_response_area(f"Error processing data: {str(e)}\n")

    def on_ticker_changed(self, ticker):
        price = self.current_prices.get(ticker, 0)
        self.price_input.setText(str(price))
        self.update_default_values(ticker)
        if self.is_databento_initialized:
            self.initialize_databento_worker()


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
        self.stop_databento_worker()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TradingApp()
    ex.show()
    sys.exit(app.exec_())