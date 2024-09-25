import sys
import json
import requests # type: ignore
import os
import math
from datetime import datetime, timedelta, date
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,  # type: ignore
                             QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, 
                             QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
                             QSpinBox, QTableWidget, QTableWidgetItem, QCheckBox)
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon, QPixmap # type: ignore
from PyQt5.QtCore import QTimer, Qt, QPoint, QSize # type: ignore
import asyncio
import aiohttp # type: ignore
import ssl
from PyQt5.QtCore import QThread, pyqtSignal # type: ignore
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

POLYGON_API_KEY = "YivSExBlbvxMQu5pPyE5Hj9Me1XCCuoE"  # Replace with your Polygon API key

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


class PutCallRatioChart(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(PutCallRatioChart, self).__init__(fig)
        self.setParent(parent)

    def update_chart(self, options_data):
        self.axes.clear()
        strikes = [option['strike_price'] for option in options_data]
        ratios = [option['put_volume'] / option['call_volume'] if option['call_volume'] != 0 else 0 for option in options_data]
        
        self.axes.plot(strikes, ratios, marker='o')
        self.axes.set_xlabel('Strike Price')
        self.axes.set_ylabel('Put-Call Ratio')
        self.axes.set_title('Put-Call Ratio by Strike Price')
        self.axes.grid(True)
        self.draw()


class OptionsDataFetcher(QThread):
    data_fetched = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, underlying, current_price, target_date, api_key, verify_ssl=True):
        super().__init__()
        self.underlying = underlying
        self.current_price = current_price
        self.target_date = target_date
        self.api_key = api_key
        self.verify_ssl = verify_ssl

    async def fetch_option_details(self, session, option):
        url = f"https://api.polygon.io/v3/reference/options/contracts/{option['ticker']}?apiKey={self.api_key}"
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                details = data.get('results', {})
                return {
                    'strike_price': option['strike_price'],
                    'expiration_date': option['expiration_date'],
                    'call_volume': details.get('day', {}).get('volume', 0),
                    'put_volume': details.get('day', {}).get('volume', 0),
                    'call_open_interest': details.get('open_interest', 0),
                    'put_open_interest': details.get('open_interest', 0),
                    'last_trade_price': details.get('last_trade', {}).get('price', 'N/A'),
                    'last_trade_time': details.get('last_trade', {}).get('sip_timestamp', 'N/A'),
                }
            else:
                return None

    async def fetch_data(self):
        url = f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={self.underlying}&expiration_date={self.target_date}&sort=strike_price&order=asc&limit=1000&apiKey={self.api_key}"
        
        # Create a custom SSL context that doesn't verify certificates if verify_ssl is False
        if not self.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        else:
            ssl_context = None

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    self.error_occurred.emit(f"Failed to fetch options data. Status code: {response.status}")
                    return
                
                data = await response.json()
                options = data.get('results', [])
                
                # Sort options by how close their strike price is to the current price
                options.sort(key=lambda x: abs(float(x['strike_price']) - self.current_price))
                
                # Select the 10 closest options
                closest_options = options[:10]
                
                # Fetch details for each option
                tasks = [self.fetch_option_details(session, option) for option in closest_options]
                options_data = await asyncio.gather(*tasks)
                
                # Filter out None values (failed requests)
                options_data = [opt for opt in options_data if opt is not None]
                
                self.data_fetched.emit(options_data)

    def run(self):
        asyncio.run(self.fetch_data())
class SettingsDialog(QDialog):
    def __init__(self, parent, api_url):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        
        layout = QFormLayout(self)
        
        self.url_input = QLineEdit(api_url)
        layout.addRow("Webhook URL:", self.url_input)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_settings(self):
        return self.url_input.text()


class TradingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trading App with Options Analysis")
        self.setGeometry(100, 100, 800, 800)
        self.api_key = "YivSExBlbvxMQu5pPyE5Hj9Me1XCCuoE" 
        self.load_settings()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Ticker selection, price input, and quantity input
        input_layout = QGridLayout()
        input_layout.addWidget(QLabel("Ticker:"), 0, 0)
        self.ticker_combo = QComboBox()
        self.ticker_combo.addItems(["MNQ", "MGC", "MES"])
        self.ticker_combo.currentTextChanged.connect(self.update_ticker)
        input_layout.addWidget(self.ticker_combo, 0, 1)
        
        input_layout.addWidget(QLabel("Price:"), 1, 0)
        self.price_input = QLineEdit("0")
        self.price_input.textChanged.connect(self.update_stop_loss)
        input_layout.addWidget(self.price_input, 1, 1)
        
        input_layout.addWidget(QLabel("Quantity:"), 2, 0)
        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setValue(1)
        input_layout.addWidget(self.quantity_input, 2, 1)
        
        main_layout.addLayout(input_layout)
        
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
        
        # Options Analysis Section
        options_layout = QVBoxLayout()
        options_header_layout = QHBoxLayout()
        options_header_layout.addWidget(QLabel("Options Analysis"))
        
        self.fetch_options_button = QPushButton("Fetch Options Data")
        self.fetch_options_button.clicked.connect(self.update_options_data)
        options_header_layout.addWidget(self.fetch_options_button)
        
        self.periodic_update_checkbox = QCheckBox("Update Periodically")
        self.periodic_update_checkbox.stateChanged.connect(self.toggle_periodic_update)
        options_header_layout.addWidget(self.periodic_update_checkbox)
        
        self.update_interval_input = QLineEdit()
        self.update_interval_input.setPlaceholderText("Update interval (seconds)")
        self.update_interval_input.setFixedWidth(150)
        options_header_layout.addWidget(self.update_interval_input)
        
        options_layout.addLayout(options_header_layout)
        
        self.options_table = QTableWidget()
        self.options_table.setColumnCount(6)
        self.options_table.setHorizontalHeaderLabels(["Strike", "Expiration", "Call Volume", "Put Volume", "Call OI", "Put OI"])
        options_layout.addWidget(self.options_table)
        
        main_layout.addLayout(options_layout)

        # Add Put-Call Ratio Chart
        self.put_call_ratio_chart = PutCallRatioChart(self, width=5, height=4)
        options_layout.addWidget(self.put_call_ratio_chart)
        
        main_layout.addLayout(options_layout)

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
            item = input_layout.itemAtPosition(i, 0)
            if item and item.widget():
                item.widget().setFixedWidth(80)
        for i in range(stop_loss_layout.rowCount()):
            item = stop_loss_layout.itemAtPosition(i, 0)
            if item and item.widget():
                item.widget().setFixedWidth(80)

        # Initialize update timer (but don't start it)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_options_data)



    def load_settings(self):
        if os.path.exists('settings.json'):
            try:
                with open('settings.json', 'r') as f:
                    settings = json.load(f)
                    self.api_url = settings.get('api_url', "https://your-api-endpoint.com/orders")
            except json.JSONDecodeError:
                self.use_default_settings()
        else:
            self.use_default_settings()

    def use_default_settings(self):
        self.api_url = "https://your-api-endpoint.com/orders"

    def save_settings(self):
        settings = {
            'api_url': self.api_url
        }
        with open('settings.json', 'w') as f:
            json.dump(settings, f, indent=2)


    def calculate_stop_loss(self, ticker, price):
        if price == 0:
            return 0, 0
        
        if ticker == "MNQ":
            points = 20
        elif ticker == "MGC":
            points = 4
        elif ticker == "MES":
            points = 10
        else:
            return 0, 0
        
        long_stop_loss = price - points
        short_stop_loss = price + points
        return long_stop_loss, short_stop_loss

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



    def open_settings(self):
        dialog = SettingsDialog(self, self.api_url)
        if dialog.exec_() == QDialog.Accepted:
            self.api_url = dialog.get_settings()
            self.save_settings()
            self.update_response_area(f"Settings updated:\nWebhook URL: {self.api_url}\n")

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


    def toggle_periodic_update(self, state):
        if state == Qt.Checked:
            try:
                interval = int(self.update_interval_input.text()) * 1000  # Convert to milliseconds
                if interval < 1000:  # Minimum 1 second interval
                    raise ValueError("Interval too short")
                self.update_timer.start(interval)
                self.update_response_area("Periodic update enabled")
            except ValueError:
                self.update_response_area("Invalid update interval. Please enter a valid number of seconds.")
                self.periodic_update_checkbox.setChecked(False)
        else:
            self.update_timer.stop()
            self.update_response_area("Periodic update disabled")

    def update_options_data(self):
        ticker = self.ticker_combo.currentText()
        if ticker == "MNQ":
            underlying = "QQQ"
        elif ticker == "MES":
            underlying = "SPY"
        else:
            self.update_response_area(f"Options data not available for {ticker}")
            self.clear_options_table()
            return

        self.update_response_area(f"Fetching options data for {underlying}...")

        # Fetch current price of the underlying
        current_price = self.fetch_current_price(underlying)
        if current_price is None:
            self.update_response_area(f"Failed to fetch price for {underlying}. Please check your API key and permissions.")
            self.clear_options_table()
            return

        self.update_response_area(f"Current price of {underlying}: ${current_price}")

        # Determine the target expiration date (next Monday if it's a weekend)
        today = date.today()
        days_to_monday = (7 - today.weekday()) % 7
        target_date = today + timedelta(days=days_to_monday)
        target_date_str = target_date.isoformat()

        # Create and start the data fetcher thread
        self.data_fetcher = OptionsDataFetcher(underlying, current_price, target_date_str, POLYGON_API_KEY, verify_ssl=False)
        self.data_fetcher.data_fetched.connect(self.update_options_table)
        self.data_fetcher.error_occurred.connect(self.update_response_area)
        self.data_fetcher.start()

        self.put_call_ratio_chart(options_data)

    def update_options_data(self):
        ticker = self.ticker_combo.currentText()
        if ticker == "MNQ":
            underlying = "QQQ"
        elif ticker == "MES":
            underlying = "SPY"
        else:
            self.update_response_area(f"Options data not available for {ticker}")
            self.clear_options_table()
            return

        self.update_response_area(f"Fetching options data for {underlying}...")

        # Fetch current price of the underlying
        current_price = self.fetch_current_price(underlying)
        if current_price is None:
            self.update_response_area(f"Failed to fetch price for {underlying}. Please check your API key and permissions.")
            self.clear_options_table()
            return

        self.update_response_area(f"Current price of {underlying}: ${current_price}")

        # Determine the target expiration date (next Monday if it's a weekend)
        today = date.today()
        days_to_monday = (7 - today.weekday()) % 7
        target_date = today + timedelta(days=days_to_monday)
        target_date_str = target_date.isoformat()

        # Fetch options data
        options_data = self.fetch_options_data(underlying, current_price, target_date_str)

        if not options_data:
            self.update_response_area("No options data available.")
            self.clear_options_table()
            return

    def update_options_table(self, options_data):
        if not options_data:
            self.update_response_area("No options data available.")
            self.clear_options_table()
            return

        underlying = self.ticker_combo.currentText()
        current_price = self.fetch_current_price(underlying)

        # Check if current_price is None
        if current_price is None:
            self.update_response_area(f"Failed to fetch current price for {underlying}.")
            current_price_str = "N/A"
        else:
            current_price_str = f"${current_price:.2f}"

        # Sort options by strike price
        options_data.sort(key=lambda x: x['strike_price'])

        # Identify option walls
        call_wall, put_wall = self.identify_option_walls(options_data)

        # Update the options table
        self.options_table.setColumnCount(10)
        self.options_table.setHorizontalHeaderLabels([
            "Strike", "Call Volume", "Put Volume", "Call OI", "Put OI", 
            "Call Wall", "Put Wall", f"{underlying} Price", "Futures Price", "Last Trade"
        ])
        self.options_table.setRowCount(len(options_data))

        for row, option in enumerate(options_data):
            strike = option['strike_price']
            self.options_table.setItem(row, 0, QTableWidgetItem(str(strike)))
            self.options_table.setItem(row, 1, QTableWidgetItem(str(option['call_volume'])))
            self.options_table.setItem(row, 2, QTableWidgetItem(str(option['put_volume'])))
            self.options_table.setItem(row, 3, QTableWidgetItem(str(option['call_open_interest'])))
            self.options_table.setItem(row, 4, QTableWidgetItem(str(option['put_open_interest'])))
            
            # Highlight walls
            call_wall_item = QTableWidgetItem("" if call_wall is None or strike != call_wall else "WALL")
            put_wall_item = QTableWidgetItem("" if put_wall is None or strike != put_wall else "WALL")
            call_wall_item.setBackground(QColor(255, 200, 200) if call_wall is not None and strike == call_wall else QColor(255, 255, 255))
            put_wall_item.setBackground(QColor(200, 255, 200) if put_wall is not None and strike == put_wall else QColor(255, 255, 255))
            self.options_table.setItem(row, 5, call_wall_item)
            self.options_table.setItem(row, 6, put_wall_item)

            # Add price translation
            self.options_table.setItem(row, 7, QTableWidgetItem(f"${strike:.2f}"))
            futures_price = self.translate_to_futures(underlying, strike)
            self.options_table.setItem(row, 8, QTableWidgetItem(f"${futures_price:.2f}"))
            
            # Add last trade info
            last_trade_price = option.get('last_trade_price', 'N/A')
            last_trade_time = option.get('last_trade_time', 'N/A')
            if last_trade_price != 'N/A':
                last_trade_info = f"${last_trade_price:.2f} @ {last_trade_time}"
            else:
                last_trade_info = "N/A"
            self.options_table.setItem(row, 9, QTableWidgetItem(last_trade_info))

        self.update_response_area(f"Options data updated for {underlying} (10 closest strikes to current price: {current_price_str})")

    def identify_option_walls(self, options_data):
        call_oi = {opt['strike_price']: opt['call_open_interest'] for opt in options_data}
        put_oi = {opt['strike_price']: opt['put_open_interest'] for opt in options_data}
        
        call_wall = max(call_oi, key=call_oi.get)
        put_wall = max(put_oi, key=put_oi.get)
        
        return call_wall, put_wall

    def translate_to_futures(self, underlying, price):
        if underlying == "SPY":
            return price * 10  # Approximate ES price
        elif underlying == "QQQ":
            return price * 40  # Approximate NQ price
        return price

    
    def clear_options_table(self):
        self.options_table.setRowCount(0)

    def update_ticker(self):
        ticker = self.ticker_combo.currentText()
        self.update_stop_loss()
        if ticker in ["MNQ", "MES"]:
            self.update_options_data()
        else:
            self.clear_options_table()
            self.update_response_area(f"Options data not available for {ticker}")

    def fetch_current_price(self, ticker):
        # Map futures to their underlying
        underlying_map = {
            "MNQ": "QQQ",
            "MES": "SPY"
        }
        
        # Use the underlying ticker if it's a future, otherwise use the ticker as is
        underlying = underlying_map.get(ticker, ticker)

        # Get yesterday's date
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        url = f"https://api.polygon.io/v1/open-close/{underlying}/{yesterday}?adjusted=true&apiKey={POLYGON_API_KEY}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return data['close']
        except Exception as e:
            self.update_response_area(f"Error fetching price for {underlying}: {str(e)}")
            return None


    def fetch_options_data(self, underlying, current_price, target_date):
        url = f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={underlying}&expiration_date={target_date}&sort=strike_price&order=asc&limit=1000&apiKey={POLYGON_API_KEY}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            options_data = []
            for option in data.get('results', []):
                # Fetch detailed data for each option
                details_url = f"https://api.polygon.io/v3/reference/options/contracts/{option['ticker']}?apiKey={POLYGON_API_KEY}"
                details_response = requests.get(details_url)
                details_response.raise_for_status()
                details_data = details_response.json().get('results', {})
                
                # Get the latest day's data
                last_trade = details_data.get('last_trade', {})
                day_data = details_data.get('day', {})
                prev_day_data = details_data.get('underlying_asset', {}).get('previous_close', {})
                
                options_data.append({
                    'strike_price': option['strike_price'],
                    'expiration_date': option['expiration_date'],
                    'call_volume': day_data.get('volume', 0) or prev_day_data.get('volume', 0),
                    'put_volume': day_data.get('volume', 0) or prev_day_data.get('volume', 0),
                    'call_open_interest': day_data.get('open_interest', 0) or prev_day_data.get('open_interest', 0),
                    'put_open_interest': day_data.get('open_interest', 0) or prev_day_data.get('open_interest', 0),
                    'last_trade_price': last_trade.get('price', 'N/A'),
                    'last_trade_time': last_trade.get('sip_timestamp', 'N/A'),
                })
            
            return options_data
        except Exception as e:
            self.update_response_area(f"Error fetching options data: {str(e)}")
            return []


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TradingApp()
    ex.show()
    sys.exit(app.exec_())
