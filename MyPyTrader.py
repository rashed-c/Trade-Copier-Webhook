import sys
import json
import requests
import os
import math 
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, 
                             QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QSpinBox, QSizePolicy)
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon, QPixmap
from PyQt5.QtCore import Qt, QSize, QPoint


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
        self.setWindowTitle("Trading App")
        self.setGeometry(100, 100, 400, 600)
        
        self.load_settings()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Ticker selection, price input, and quantity input
        input_layout = QGridLayout()
        input_layout.addWidget(QLabel("Ticker:"), 0, 0)
        self.ticker_combo = QComboBox()
        self.ticker_combo.addItems(["MNQ", "MGC", "MES"])
        self.ticker_combo.currentTextChanged.connect(self.update_stop_loss)
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TradingApp()
    ex.show()
    sys.exit(app.exec_())
