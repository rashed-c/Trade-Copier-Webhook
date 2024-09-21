# PyQt5 Trading Application

This is a simple trading application built with PyQt5 that allows users to send buy, sell, and exit trade orders for futures contracts using a webhook.


![image](https://github.com/user-attachments/assets/4da1d766-51fc-4899-aacf-b368b0953111)


## Features

- Select from multiple futures contracts (MNQ, MGC, MES)
- Enter trade price and quantity
- Automatically calculate stop loss prices for long and short positions
- Choose stop loss type (Market, Limit, Trailing)
- Send buy, sell, and exit trade orders via webhook
- View order responses in real-time
- Configure webhook URL for order submission

## Requirements

- Python 3.6+
- PyQt5
- requests

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/pyqt5-trading-app.git
   cd pyqt5-trading-app
   ```

2. Create a virtual environment (optional but recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```
   python trading_app.py
   ```

2. Use the interface to:
   - Select a futures contract
   - Enter the trade price and quantity
   - Choose a stop loss type
   - Click BUY, SELL, or EXIT TRADE to send orders

3. Configure the webhook URL by clicking the settings (gear) icon in the top right corner.

## Webhook Order Submission

This application uses a webhook to submit orders to an external system. Here's how it works:

1. **Webhook Configuration**: 
   - The webhook URL is configured in the settings dialog.
   - This URL represents the endpoint where orders will be sent.

2. **Order Payload**:
   When an order is submitted, the application constructs a JSON payload with the following structure:
   ```json
   {
     "ticker": "MNQ1!",
     "action": "buy",
     "quantity": 1,
     "price": 15000.5,
     "sentiment": "long",
     "stopLoss": {
       "type": "stop",
       "stopPrice": 14980.5
     }
   }
   ```
   - The `ticker` field is the selected futures contract.
   - `action` can be "buy", "sell", or "exit".
   - `quantity` is included for buy and sell orders, but not for exit orders.
   - `price` is included if it's greater than 0.
   - `sentiment` is "long" for buy orders and "short" for sell orders.
   - `stopLoss` is included for buy and sell orders if a stop loss is set.

3. **HTTP Request**:
   - The application sends a POST request to the configured webhook URL.
   - The order payload is sent as JSON in the request body.

4. **Response Handling**:
   - The application expects a JSON response from the webhook.
   - A successful response should have a structure similar to:
     ```json
     {
       "success": true,
       "id": "d1c51986-d1f3-4aff-b7b8-d54f51523218",
       "logId": "264703e9-038b-495a-8d79-b18876bf2497",
       "payload": {
         "ticker": "MNQ1!",
         "action": "buy"
       }
     }
     ```
   - The response is displayed in the application's response area.

5. **Error Handling**:
   - If the webhook request fails, an error message is displayed in the response area.

Note: Ensure that your webhook endpoint is properly configured to receive and process these order payloads. The exact implementation of the webhook endpoint will depend on your trading infrastructure.

## Configuration

The application stores its configuration, including the webhook URL, in a `settings.json` file. This file is created automatically when you first run the application and update the settings.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
