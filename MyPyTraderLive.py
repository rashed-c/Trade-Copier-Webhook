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



# class DatabentoWorker(QThread):
#     data_received = pyqtSignal(object)
#     symbol_mapped = pyqtSignal(object)

#     def __init__(self, key, dataset, schema, symbols):
#         super().__init__()
#         self.key = key
#         self.dataset = dataset
#         self.schema = schema
#         self.symbols = symbols
#         self.is_running = True
#         self.client = None

#     def run(self):
#         try:
#             self.client = db.Live(key=self.key)
#             self.client.subscribe(
#                 dataset=self.dataset,
#                 schema=self.schema,
#                 stype_in="continuous",
#                 symbols=self.symbols
#             )
#             for message in self.client:
#                 if not self.is_running:
#                     break
#                 if isinstance(message, db.SymbolMappingMsg):
#                     self.symbol_mapped.emit(message)
#                 else:
#                     self.data_received.emit(message)
#         except Exception as e:
#             print(f"Error in Databento streaming: {str(e)}")
#         finally:
#             if self.client:
#                 self.client.stop()

#     def stop(self):
#         self.is_running = False
#         if self.client:
#             self.client.stop()

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
                    # Try to determine which subscription this message belongs to
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

# class DatabentoWorker(QThread):
#     data_received = pyqtSignal(str, object)  # Signal now includes subscription ID
#     symbol_mapped = pyqtSignal(str, object)  # Signal now includes subscription ID
#     error_occurred = pyqtSignal(str, str)
#     def __init__(self, key):
#         super().__init__()
#         self.key = key
#         self.subscriptions = {}
#         self.is_running = True
#         self.client = None

#     def add_subscription(self, subscription_id, dataset, schema, symbols, stype_in=None):
#         self.subscriptions[subscription_id] = {
#             'dataset': dataset,
#             'schema': schema,
#             'stype_in': stype_in,
#             'symbols': symbols
#         }

#     def run(self):
#         try:
#             self.client = db.Live(key=self.key)
#             for sub_id, sub_info in self.subscriptions.items():
#                 print(f"Subscribing to {sub_id}: {sub_info}")
#                 subscribe_params = {
#                     'dataset': sub_info['dataset'],
#                     'schema': sub_info['schema'],
#                     'symbols': sub_info['symbols']
#                 }
#                 if 'stype_in' in sub_info and sub_info['stype_in']:
#                     subscribe_params['stype_in'] = sub_info['stype_in']
                
#                 self.client.subscribe(**subscribe_params)
            
#             for message in self.client:
#                 if not self.is_running:
#                     break
#                 if isinstance(message, db.SymbolMappingMsg):
#                     print(f"Received SymbolMappingMsg: {message}")
#                     for sub_id in self.subscriptions:
#                         self.symbol_mapped.emit(sub_id, message)
#                 else:
#                     for sub_id in self.subscriptions:
#                         self.data_received.emit(sub_id, message)
#         except Exception as e:
#             print(f"Error in Databento streaming: {str(e)}")
#         finally:
#             if self.client:
#                 self.client.stop()
        # try:
        #     self.client = db.Live(key=self.key)
        #     for sub_id, sub_info in self.subscriptions.items():
        #         self.client.subscribe(
        #             dataset=sub_info['dataset'],
        #             schema=sub_info['schema'],
        #             stype_in=sub_info['stype_in'],
        #             symbols=sub_info['symbols']
        #         )
                 
        #     for message in self.client:
        #         if not self.is_running:
        #             break
        #         for sub_id in self.subscriptions:
        #             if isinstance(message, db.SymbolMappingMsg):
        #                 self.symbol_mapped.emit(sub_id, message)
        #             else:
        #                 self.data_received.emit(sub_id, message)
        # except Exception as e:
        #     print(f"Error in Databento streaming: {str(e)}")
        # finally:
        #     if self.client:
        #         self.client.stop()

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
        
        # Initialize Databento worker
        self.databento_worker = None
        self.is_databento_initialized = False
        
        # Define the symbol map for continuous contracts
        self.symbol_map = {
            "MNQ": "MNQ.c.0",
            "MGC": "MGC.c.0",
            "MES": "MES.c.0"
        }
        
        # Initialize instrument_id map and current prices
        self.instrument_id_map = {}
        self.current_prices = {ticker: 0 for ticker in self.symbol_map}
        
        # Set up the UI
        self.setup_ui()
        
        # Initialize price and stop loss fields
        self.initialize_price_and_stoploss()

        #Databento key
        self.databento_key = "db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL"
        
        # Usage



    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Ticker selection, price input, and quantity input
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
        self.quantity_input.setValue(1)
        input_layout.addWidget(self.quantity_input, 2, 1)
        
        main_layout.addLayout(input_layout)
        
        # Databento update controls
        databento_layout = QHBoxLayout()
        self.update_checkbox = QCheckBox("Enable price updates")
        self.update_checkbox.stateChanged.connect(self.toggle_price_updates)
        databento_layout.addWidget(self.update_checkbox)
        
     
        main_layout.addLayout(databento_layout)
        
        # StopLoss inputs and type selection
        stop_loss_layout = QGridLayout()
        stop_loss_layout.addWidget(QLabel("Long StopLoss:"), 0, 0)
        self.long_stop_loss_input = QLineEdit("0")
        self.long_stop_loss_input.setReadOnly(True)
        stop_loss_layout.addWidget(self.long_stop_loss_input, 0, 1)
        
        stop_loss_layout.addWidget(QLabel("Short StopLoss:"), 1, 0)
        self.short_stop_loss_input = QLineEdit("0")
        self.short_stop_loss_input.setReadOnly(True)
        stop_loss_layout.addWidget(self.short_stop_loss_input, 1, 1)
        
        stop_loss_layout.addWidget(QLabel("StopLoss Type:"), 2, 0)
        self.stop_loss_type_combo = QComboBox()
        self.stop_loss_type_combo.addItems(["Market", "Limit", "Trailing"])
        stop_loss_layout.addWidget(self.stop_loss_type_combo, 2, 1)
        
        main_layout.addLayout(stop_loss_layout)
        
        # Buy, Sell, and Exit buttons
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
        button_layout.addWidget(self.exit_button, 1, 0, 1, 2)  # Span two columns
        
        main_layout.addLayout(button_layout)
        
        # Settings button
        settings_layout = QHBoxLayout()
        settings_layout.addStretch()
        self.settings_button = QPushButton()
        self.settings_button.setIcon(create_gear_icon())
        self.settings_button.setFixedSize(QSize(30, 30))
        self.settings_button.clicked.connect(self.open_settings)
        settings_layout.addWidget(self.settings_button)
        main_layout.addLayout(settings_layout)
        
        # Response area
        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        main_layout.addWidget(self.response_area)
        
        # Set a fixed width for the labels to align all fields
        for i in range(input_layout.rowCount()):
            input_layout.itemAtPosition(i, 0).widget().setFixedWidth(80)
        for i in range(stop_loss_layout.rowCount()):
            stop_loss_layout.itemAtPosition(i, 0).widget().setFixedWidth(80)
        
        # # Options Time and Sales section
        # options_layout = QVBoxLayout()
        # options_layout.addWidget(QLabel("Options Time and Sales"))
        
        # self.options_table = QTableWidget()
        # self.options_table.setColumnCount(6)
        # self.options_table.setHorizontalHeaderLabels(["Time", "Symbol", "Strike", "Call/Put", "Price", "Volume"])
        # options_layout.addWidget(self.options_table)
        
        # main_layout.addLayout(options_layout)

        #self.get_options_data()
    def initialize_price_and_stoploss(self):
        initial_ticker = self.ticker_combo.currentText()
        initial_price = self.current_prices[initial_ticker]
        self.update_price_and_stop_loss(initial_ticker, initial_price)



    

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

    def open_settings(self):
        dialog = SettingsDialog(self, self.api_url, self.databento_key)
        if dialog.exec_() == QDialog.Accepted:
            self.api_url, self.databento_key = dialog.get_settings()
            self.save_settings()
            self.update_response_area(f"Settings updated:\nWebhook URL: {self.api_url}\nDatabento API Key: {'*' * len(self.databento_key)}\n")
            
            # Reinitialize Databento client with new API key
            self.initialize_databento_client()

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


    def update_stop_loss(self):
        try:
            ticker = self.ticker_combo.currentText()
            price = float(self.price_input.text())
            long_stop_loss, short_stop_loss = self.calculate_stop_loss(ticker, price)
            self.long_stop_loss_input.setText(f"{long_stop_loss:.2f}")
            self.short_stop_loss_input.setText(f"{short_stop_loss:.2f}")
        except ValueError:
            self.long_stop_loss_input.setText("0")
            self.short_stop_loss_input.setText("0")

    def get_stop_loss_type(self, gui_type):
        if gui_type == "Market":
            return "stop"
        elif gui_type == "Limit":
            return "stop_limit"
        elif gui_type == "Trailing":
            return "trailing_stop"
        else:
            return "stop"  # Default to "stop" if unknown type

    def update_response_area(self, text):
        self.response_area.append(text)
        self.response_area.verticalScrollBar().setValue(
            self.response_area.verticalScrollBar().maximum()
        )



    def send_order(self, action):
        ticker = self.ticker_combo.currentText()
        if ticker == "MNQ":
            ticker = "MNQ1!"
        try:
            price = float(self.price_input.text())
            quantity = self.quantity_input.value()
            stop_loss = float(self.long_stop_loss_input.text()) if action == "buy" else float(self.short_stop_loss_input.text())
        except ValueError:
            self.update_response_area("Error: Invalid input for price or stop loss.\n")
            return
        
        order = {
            "ticker": ticker,
            "action": action
        }
        
        if action != "exit":
            order["quantity"] = quantity
            if price > 0:
                order["price"] = price
        
        if action in ["buy", "sell"]:
            order["sentiment"] = "long" if action == "buy" else "short"
            if stop_loss != 0:
                stop_loss_type = self.stop_loss_type_combo.currentText()
                order["stopLoss"] = {
                    "type": self.get_stop_loss_type(stop_loss_type),
                    "stopPrice": stop_loss
                }
        
        try:
            response = requests.post(self.api_url, json=order)
            response.raise_for_status()
            
            response_data = response.json()
            if response_data.get("success"):
                response_text = f"{action.capitalize()} order sent successfully!\n"
                response_text += "Response:\n"
                response_text += f"  Order ID: {response_data.get('id', 'N/A')}\n"
                response_text += f"  Log ID: {response_data.get('logId', 'N/A')}\n"
                
                payload = response_data.get('payload', {})
                response_text += "  Details:\n"
                for key, value in payload.items():
                    response_text += f"    {key.capitalize()}: {value}\n"
                
                response_text += "\n"
            else:
                response_text = f"Error sending {action} order: Unsuccessful response from server\n"
                response_text += f"Response: {json.dumps(response_data, indent=2)}\n\n"
            
            self.update_response_area(response_text)
        except requests.RequestException as e:
            error_text = f"Error sending {action} order: {str(e)}\n\n"
            self.update_response_area(error_text)

  

    
    # def initialize_databento_worker(self):
    #     try:
    #         symbols = list(self.symbol_map.values())
    #         self.update_response_area(f"Subscribing to symbols: {symbols}\n")

    #         self.databento_worker = DatabentoWorker(
    #             key=self.databento_key,
    #             dataset="GLBX.MDP3",
    #             schema="ohlcv-1s",
    #             symbols=symbols
    #         )
    #         self.databento_worker.data_received.connect(self.handle_databento_data)
    #         self.databento_worker.symbol_mapped.connect(self.handle_symbol_mapping)
    #         self.databento_worker.start()
    #         self.is_databento_initialized = True
    #         self.update_response_area("Databento worker initialized. Starting to receive price updates.\n")
    #     except Exception as e:
    #         self.update_response_area(f"Error initializing Databento worker: {str(e)}\n")
    #         self.databento_worker = None
    #         self.is_databento_initialized = False
    #         self.update_checkbox.setChecked(False)


    
            
    def initialize_databento_worker(self):        
        try:
            self.databento_worker = DatabentoWorker(key=self.databento_key)
            
            # Add subscription for existing functionality
            symbols = list(self.symbol_map.values())
            # resolved_symbols = resolve_symbols(self, symbols)
            self.databento_worker.add_subscription(
                subscription_id="main",
                dataset="GLBX.MDP3",
                schema="ohlcv-1s",
                stype_in="continuous",
                symbols=symbols
            )
            
            # NQ_ES_OPT_Symbols = []
            # last_friday = self.get_last_friday()
            # current_price = self.get_friday_closing_price(last_friday, "ES.c.0")
            # #current_price = 5791  # Replace with actual current price of ESZ4
            # ES_OPT_List = self.get_frontMonth_options(current_price, underlying="ESZ4")
            # NQ_ES_OPT_Symbols.append(ES_OPT_List)
            
            # current_price = self.get_friday_closing_price(last_friday, "NQ.c.0")
            # #current_price = 20221  # Replace with actual current price of ESZ4
            # NQ_OPT_List = self.get_frontMonth_options(current_price, underlying="NQZ4")
            # NQ_ES_OPT_Symbols.append(NQ_OPT_List)



            # #Add subscription for options data
            # self.databento_worker.add_subscription(
            #     subscription_id="options",
            #     dataset="GLBX.MDP3",
            #     schema="trades",
            #     stype_in="raw_symbol",
            #     symbols=NQ_ES_OPT_Symbols
            #     # symbols=["NQ.OPT", "ES.OPT"]
            # )
            
            self.databento_worker.data_received.connect(self.handle_databento_data)
            self.databento_worker.symbol_mapped.connect(self.handle_symbol_mapping)
            self.databento_worker.start()
            
            self.is_databento_initialized = True
            self.update_response_area("Databento worker initialized. Starting to receive price updates.\n")
        except Exception as e:
            self.update_response_area(f"Error initializing Databento worker: {str(e)}\n")
            self.databento_worker = None
            self.is_databento_initialized = False
            self.update_checkbox.setChecked(False)

    def get_last_friday(self):
        today = datetime.now()
        days_since_friday = (today.weekday() - 4) % 7
        last_friday = today - timedelta(days=days_since_friday)
        return last_friday


    def get_friday_closing_price(self, last_friday, symbol, dataset="GLBX.MDP3", key="db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL"):
        client = db.Historical(key)
        
        start_date = last_friday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=1)  # Next day
        
        # Query data using OHLCV schema
        df = client.timeseries.get_range(
            dataset=dataset,
            symbols=[symbol],
            stype_in="continuous",
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            schema="ohlcv-1d"
        ).to_df()
        
        # Get the closing price
        if not df.empty:
            closing_price = df['close'].iloc[0]
            print(f"The closing price for {symbol} on last Friday was: {closing_price}")
            return closing_price
        else:
            return None

       
        


    # # Example usage
    # symbol = "ES.c.0"  # E-mini S&P 500 futures
    # closing_price = get_friday_closing_price(symbol)
    # print(f"The closing price for {symbol} on last Friday was: {closing_price}")


    def get_frontMonth_options(self, current_price, underlying):
        symbol_list = []
        client = db.Historical(key="db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL")
        definitions = client.timeseries.get_range(
            dataset=db.Dataset.GLBX_MDP3,
            schema=db.Schema.DEFINITION,
            start="2024-09-26",
        )
        
        # Convert to a DataFrame
        df = definitions.to_df()
        
        # Select all instruments with a security type of OOF (options-on-futures)
        df = df[df["security_type"] == "OOF"]
        
        # Select only options with an ESZ4 underlying
        df = df[df["underlying"] == underlying]
        
        # Convert expiration to datetime and strike_price to float
        df['expiration'] = pd.to_datetime(df['expiration'])
        df['strike_price'] = df['strike_price'].astype(float)
        
        # Filter for options within 10% of the current price
        df = df[(df['strike_price'] >= 0.95 * current_price) & 
                (df['strike_price'] <= 1.05 * current_price)]
        
        # Create a view for printing
        result = df[["raw_symbol", "underlying", "instrument_class", "strike_price", "expiration"]]
        result = result.sort_values(["expiration", "strike_price"])

        
        # Print the options
        #print(f"{len(result):,d}", "relevant option(s) for ESZ4")
        for symbol in result.raw_symbol:
            symbol_list.append(symbol)
        #print(symbol_list)
        return(symbol_list)
    
        # client = db.Historical(key="db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL")

        # definitions = client.timeseries.get_range(
        #     dataset=db.Dataset.GLBX_MDP3,
        #     schema=db.Schema.DEFINITION,
        #     start="2024-09-26",
        # )

        # df = definitions.to_df()

        # # Select all instruments with a security type of OOF (options-on-futures)
        # df = df[df["security_type"] == "OOF"]
        
        # # Select only options with an ESZ4 underlying
        # df = df[df["underlying"] == "ESZ4"]

        #     # Convert expiration to datetime
        # df['expiration'] = pd.to_datetime(df['expiration'])
        
        # # Get the earliest expiration date (this should be the front month expiration)
        # front_month_expiry = df['expiration'].min()
        
        # # Filter for only the front month options
        # df = df[df['expiration'] == front_month_expiry]
        
        # # Create a view for printing
        # result = df[["raw_symbol", "underlying", "instrument_class", "strike_price", "expiration"]]
        # result = result.sort_values("strike_price")
        # raw_es_symbols = []
        # for raw_symbol in result.expiration:
        #     print(raw_symbol)

        
        # # Print the options
        # print(f"{len(result):,d}", "front month option(s) for ESZ4")
        # print(result.raw_symbol, result.underlying)

        #print (raw_es_symbols)

        # # Then, convert to a DataFrame
        # df = definitions.to_df()

        # # Now, select all instruments with a security type of OOF (options-on-futures)
        # df = df[df["security_type"] == "OOF"]

        # # And select only options with an ESM4 underlying
        # df = df[df["underlying"] == "ESZ4"]

        # # Then, create a view for printing
        # result = df[["raw_symbol", "underlying", "instrument_class", "strike_price", "expiration"]]
        # result = result.sort_values("strike_price")

        # # Finally, print the options
        # print(f"{len(result):,d}", "option(s) for ESM4")
        # print(result)
    
    
    def get_options_data(self):


        
        UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
        SPECIAL_TIMESTAMP = UNIX_EPOCH - timedelta(microseconds=1)  # This is as close as we can get with timedelta

        SPECIAL_TIMESTAMP = -1

        def format_timestamp(ts):
            if ts == SPECIAL_TIMESTAMP:
                return "Indefinite"
            # Convert nanoseconds to seconds and create a datetime object
            dt = datetime.fromtimestamp(ts / 1e9, tz=timezone.utc)
            return dt.isoformat()



        client_live = db.Live(key="db-4cBdtNdAxE9CBR3HgFuqJDidcfbrL")


        client_live.subscribe(
            dataset="GLBX.MDP3",       # Ensure this is the correct dataset for futures options
            schema="TBBO",              # Market By Order schema; change if needed
            symbols="NQ.OPT,ES.OPT",            # Specify the options symbol (e.g., ES for E-mini S&P options)
            stype_in="parent",        # Subscription type; adjust as necessary
            snapshot= False            # Request snapshot data
        )


        MIN_ORDER_SIZE = 10  # Adjust this value as needed

        # Process the incoming messages
        for msg in client_live:
            if hasattr(msg, 'records'):
                # This appears to be a TBBO message pack
                for record in msg.records:
                    if hasattr(record, 'bid_size') and hasattr(record, 'ask_size'):
                        if record.bid_size >= MIN_ORDER_SIZE or record.ask_size >= MIN_ORDER_SIZE:
                            print(f"Large order for {record.symbol}: Bid Size: {record.bid_size}, Ask Size: {record.ask_size}")
                            print(f"Bid Price: {record.bid_px}, Ask Price: {record.ask_px}")
                            if hasattr(record, 'ts_event'):
                                print(f"Timestamp: {record.ts_event}")
            elif hasattr(msg, 'message'):
                # This might be an error message
                print(f"Error message received: {msg.message}")
            elif hasattr(msg, 'code') and hasattr(msg, 'msg'):
                # This is a SystemMsg
                print(f"System message received: Code {msg.code}, Message: {msg.msg}")
                if hasattr(msg, 'is_heartbeat') and msg.is_heartbeat:
                    print("This is a heartbeat message.")
            elif hasattr(msg, 'stype_in_symbol') and hasattr(msg, 'stype_out_symbol'):
                # This is a SymbolMappingMsg
                start_time = format_timestamp(msg.start_ts)
                end_time = format_timestamp(msg.end_ts)
                print(f"Symbol mapping received: {msg.stype_in_symbol} -> {msg.stype_out_symbol}")
                print(f"Valid from {start_time} to {end_time}")
                if start_time == "Indefinite" and end_time == "Indefinite":
                    print("This appears to be a permanent symbol mapping.")
            else:
                print(f"Received unexpected message type: {type(msg)}")
                print("Attributes:", dir(msg))


    # def handle_options_data(self, message):
    #     try:
    #         time = message.ts_event
    #         symbol = message.symbol
    #         strike = message.strike
    #         option_type = "Call" if message.call_put == 0 else "Put"
    #         price = message.price / 10000  # Assuming price is in 10000ths
    #         volume = message.volume

    #         row_position = self.options_table.rowCount()
    #         self.options_table.insertRow(row_position)
    #         self.options_table.setItem(row_position, 0, QTableWidgetItem(str(time)))
    #         self.options_table.setItem(row_position, 1, QTableWidgetItem(symbol))
    #         self.options_table.setItem(row_position, 2, QTableWidgetItem(str(strike)))
    #         self.options_table.setItem(row_position, 3, QTableWidgetItem(option_type))
    #         self.options_table.setItem(row_position, 4, QTableWidgetItem(f"{price:.2f}"))
    #         self.options_table.setItem(row_position, 5, QTableWidgetItem(str(volume)))

    #         # Keep only the last 100 rows
    #         if self.options_table.rowCount() > 100:
    #             self.options_table.removeRow(0)

    #         self.options_table.scrollToBottom()
    #     except Exception as e:
    #         self.update_response_area(f"Error processing options data: {str(e)}\n")

    
    def stop_databento_worker(self):
        if self.databento_worker:
            self.databento_worker.stop()
            self.databento_worker.wait()
            self.databento_worker = None
        self.is_databento_initialized = False
        self.update_response_area("Databento connection stopped. Price updates disabled.\n")


    # def handle_symbol_mapping(self, message):
    #     instrument_id = message.instrument_id
    #     continuous_symbol = message.stype_in_symbol
    #     raw_symbol = message.stype_out_symbol

    #     self.instrument_id_map[instrument_id] = continuous_symbol
    #     self.update_response_area(f"Symbol Mapping: {continuous_symbol} ({raw_symbol}) has an instrument ID of {instrument_id}\n")
    #     self.print_debug_info()


    def handle_symbol_mapping(self, subscription_id, message):
        print(f"Handling symbol mapping for subscription: {subscription_id}")
        print(f"Message: {message}")
        
        if subscription_id == "main":
            instrument_id = message.instrument_id
            continuous_symbol = message.stype_in_symbol
            raw_symbol = message.stype_out_symbol
            self.instrument_id_map[instrument_id] = continuous_symbol
            self.update_response_area(f"Symbol Mapping: {continuous_symbol} ({raw_symbol}) has an instrument ID of {instrument_id}\n")
            self.print_debug_info()
        elif subscription_id == "options":
            print(f"Options Symbol Mapping: {message.stype_in_symbol} mapped to {message.stype_out_symbol}")
        else:
            print(f"Unexpected subscription ID in symbol mapping: {subscription_id}")


    # def handle_symbol_mapping(self, subscription_id, message):
    #     if subscription_id == "main":
    #         print("main")
    #         # instrument_id = message.instrument_id
    #         # continuous_symbol = message.stype_in_symbol
    #         # raw_symbol = message.stype_out_symbol

    #         # self.instrument_id_map[instrument_id] = continuous_symbol
    #         # self.update_response_area(f"Symbol Mapping: {continuous_symbol} ({raw_symbol}) has an instrument ID of {instrument_id}\n")
    #         # self.print_debug_info()
    #     elif subscription_id == "options":
    #         print("options")
  

    def handle_databento_data(self, subscription_id, message):
        if subscription_id == "main":
            # Handle data for main subscription (existing functionality)
            # Your existing code here
            try:
                if hasattr(message, 'instrument_id'):
                    instrument_id = message.instrument_id
                    symbol = self.instrument_id_map.get(instrument_id)
                    
                    scale_factor = 1000000000  # 1 billion

                    if symbol:
                        ticker = next((key for key, value in self.symbol_map.items() if value == symbol), None)
                        
                        if ticker and hasattr(message, 'close'):
                            close_price = message.close / scale_factor
                            
                            # Store the latest price for this ticker
                            self.current_prices[ticker] = close_price

                            # Only update UI if this is the currently selected ticker
                            if ticker == self.ticker_combo.currentText():
                                self.price_input.setText(f"{close_price:.2f}")
                                self.update_stop_loss()

                            self.update_response_area(f"Updated {ticker} price: {close_price:.2f}\n")
                            
                            if hasattr(message, 'open') and hasattr(message, 'high') and hasattr(message, 'low'):
                                open_price = message.open / scale_factor
                                high_price = message.high / scale_factor
                                low_price = message.low / scale_factor
                                self.update_response_area(f"OHLCV: Open: {open_price:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Close: {close_price:.2f}, Volume: {message.volume}\n")
                            
                            if hasattr(message, 'ts_event'):
                                self.update_response_area(f"Timestamp: {message.ts_event}\n")
                        else:
                            self.update_response_area(f"Received data for unmatched ticker: {ticker}\n")
                    else:
                        open_price = message.open / scale_factor if hasattr(message, 'open') else 'N/A'
                        high_price = message.high / scale_factor if hasattr(message, 'high') else 'N/A'
                        low_price = message.low / scale_factor if hasattr(message, 'low') else 'N/A'
                        close_price = message.close / scale_factor if hasattr(message, 'close') else 'N/A'
                        
                        self.update_response_area(f"Received data for unmatched instrument_id: {instrument_id}\n")
                        self.update_response_area(f"OHLCV data for unmatched ID:\n")
                        self.update_response_area(f"  Raw - Open: {message.open}, High: {message.high}, Low: {message.low}, Close: {message.close}\n")
                        self.update_response_area(f"  Scaled - Open: {open_price:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Close: {close_price:.2f}, Volume: {message.volume}\n")
                else:
                    self.update_response_area("Received message without instrument_id attribute\n")
                
                self.print_debug_info()
            except Exception as e:
                self.update_response_area(f"Error processing data: {str(e)}\n")
            pass
        elif subscription_id == "options":
            # Handle data for options subscription
            if hasattr(message, 'records'):
                for record in message.records:
                    if hasattr(record, 'bid_size') and hasattr(record, 'ask_size'):
                        if record.bid_size >= 10 or record.ask_size >= 10:
                            print(f"Large order for {record.symbol}: Bid Size: {record.bid_size}, Ask Size: {record.ask_size}")
                            print(f"Bid Price: {record.bid_px}, Ask Price: {record.ask_px}")
                            if hasattr(record, 'ts_event'):
                                print(f"Timestamp: {record.ts_event}")

    # def handle_databento_data(self, message):
    #     try:
    #         if hasattr(message, 'instrument_id'):
    #             instrument_id = message.instrument_id
    #             symbol = self.instrument_id_map.get(instrument_id)
                
    #             scale_factor = 1000000000  # 1 billion

    #             if symbol:
    #                 ticker = next((key for key, value in self.symbol_map.items() if value == symbol), None)
                    
    #                 if ticker and hasattr(message, 'close'):
    #                     close_price = message.close / scale_factor
                        
    #                     # Store the latest price for this ticker
    #                     self.current_prices[ticker] = close_price

    #                     # Only update UI if this is the currently selected ticker
    #                     if ticker == self.ticker_combo.currentText():
    #                         self.price_input.setText(f"{close_price:.2f}")
    #                         self.update_stop_loss()

    #                     self.update_response_area(f"Updated {ticker} price: {close_price:.2f}\n")
                        
    #                     if hasattr(message, 'open') and hasattr(message, 'high') and hasattr(message, 'low'):
    #                         open_price = message.open / scale_factor
    #                         high_price = message.high / scale_factor
    #                         low_price = message.low / scale_factor
    #                         self.update_response_area(f"OHLCV: Open: {open_price:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Close: {close_price:.2f}, Volume: {message.volume}\n")
                        
    #                     if hasattr(message, 'ts_event'):
    #                         self.update_response_area(f"Timestamp: {message.ts_event}\n")
    #                 else:
    #                     self.update_response_area(f"Received data for unmatched ticker: {ticker}\n")
    #             else:
    #                 open_price = message.open / scale_factor if hasattr(message, 'open') else 'N/A'
    #                 high_price = message.high / scale_factor if hasattr(message, 'high') else 'N/A'
    #                 low_price = message.low / scale_factor if hasattr(message, 'low') else 'N/A'
    #                 close_price = message.close / scale_factor if hasattr(message, 'close') else 'N/A'
                    
    #                 self.update_response_area(f"Received data for unmatched instrument_id: {instrument_id}\n")
    #                 self.update_response_area(f"OHLCV data for unmatched ID:\n")
    #                 self.update_response_area(f"  Raw - Open: {message.open}, High: {message.high}, Low: {message.low}, Close: {message.close}\n")
    #                 self.update_response_area(f"  Scaled - Open: {open_price:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Close: {close_price:.2f}, Volume: {message.volume}\n")
    #         else:
    #             self.update_response_area("Received message without instrument_id attribute\n")
            
    #         self.print_debug_info()
    #     except Exception as e:
    #         self.update_response_area(f"Error processing data: {str(e)}\n")

    def calculate_stop_loss(self, ticker, price):
        if price == 0:
            return 0, 0
        
        if ticker == "MNQ":
            points = 20
        elif ticker == "GC":
            points = 4
        elif ticker == "ES":
            points = 10
        else:
            return 0, 0
        
        long_stop_loss = price - points
        short_stop_loss = price + points
        return long_stop_loss, short_stop_loss

    def print_debug_info(self):
        self.update_response_area("Debug Information:\n")
        self.update_response_area(f"Symbol Map: {self.symbol_map}\n")
        self.update_response_area(f"Instrument ID Map: {self.instrument_id_map}\n")
        self.update_response_area(f"Is Databento Initialized: {self.is_databento_initialized}\n")
        self.update_response_area(f"Current Ticker: {self.ticker_combo.currentText()}\n")

    def handle_ohlcv_data(self, message):
        try:
            instrument_id = getattr(message, 'instrument_id', None)

            self.update_response_area(f"Received OHLCV data:\n")
            self.update_response_area(f"  Instrument ID: {instrument_id}\n")
            self.update_response_area(f"  Open: {message.open}\n")
            self.update_response_area(f"  High: {message.high}\n")
            self.update_response_area(f"  Low: {message.low}\n")
            self.update_response_area(f"  Close: {message.close}\n")
            self.update_response_area(f"  Volume: {message.volume}\n")
            self.update_response_area(f"  Timestamp: {message.ts_event}\n")

            symbol = self.instrument_id_map.get(instrument_id)
            if symbol:
                ticker = next((key for key, value in self.symbol_map.items() if value == symbol), None)
                if ticker:
                    # Assuming prices are in 100000ths now (adjust as needed)
                    scale_factor = 100000
                    open_price = message.open / scale_factor
                    high_price = message.high / scale_factor
                    low_price = message.low / scale_factor
                    close_price = message.close / scale_factor
                    
                    # Use the close price as the current price
                    self.price_input.setText(f"{close_price:.2f}")
                    self.update_response_area(f"Updated {ticker} price: {close_price:.2f}\n")
                    self.update_response_area(f"OHLCV: Open: {open_price:.2f}, High: {high_price:.2f}, Low: {low_price:.2f}, Close: {close_price:.2f}, Volume: {message.volume}\n")
                    self.update_response_area(f"Timestamp: {message.ts_event}\n")
                    
                    # Update stop loss values
                    self.update_stop_loss()
                else:
                    self.update_response_area(f"Matched symbol {symbol} but no corresponding ticker found.\n")
            else:
                self.update_response_area(f"Received OHLCV data for unmatched instrument_id: {instrument_id}\n")
            
            self.print_debug_info()
        except Exception as e:
            self.update_response_area(f"Error processing OHLCV data: {str(e)}\n")
            self.update_response_area(f"Message attributes: {dir(message)}\n")

    def update_price_and_stop_loss(self, ticker, price):
        self.price_input.setText(f"{price:.2f}")
        long_stop_loss, short_stop_loss = self.calculate_stop_loss(ticker, price)
        self.long_stop_loss_input.setText(f"{long_stop_loss:.2f}")
        self.short_stop_loss_input.setText(f"{short_stop_loss:.2f}")
        self.update_response_area(f"Updated UI for {ticker}: Price: {price:.2f}, Long Stop: {long_stop_loss:.2f}, Short Stop: {short_stop_loss:.2f}\n")

    def on_ticker_changed(self, ticker):
        price = self.current_prices.get(ticker, 0)
        self.update_price_and_stop_loss(ticker, price)
    
    def calculate_stop_loss(self, ticker, price):
        if price == 0:
            return 0, 0
        
        if ticker == "MNQ":
            points = 20
        elif ticker == "GC":
            points = 4
        elif ticker == "ES":
            points = 10
        else:
            return 0, 0
        
        long_stop_loss = price - points
        short_stop_loss = price + points
        return long_stop_loss, short_stop_loss
    
    def toggle_price_updates(self, state):
        if state == Qt.Checked:
            self.update_response_area("Initializing Databento connection...\n")
            self.initialize_databento_worker()
        else:
            self.update_response_area("Stopping Databento connection...\n")
            self.stop_databento_worker()

    def closeEvent(self, event):
        self.stop_databento_worker()
        # self.stop_price_updates()
        # event.accept()
        if self.databento_worker:
            self.databento_worker.stop()
            self.databento_worker.wait()
        self.update_response_area("Price updates stopped.\n")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TradingApp()
    ex.show()
    sys.exit(app.exec_())