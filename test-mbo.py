# import os
# import databento as db
# # from databento.common.enums import SType
# # from databento.live.exceptions import LiveError

# # Replace with your Databento API key
# API_KEY = os.getenv("db-aPX3iuLkKyURgLvEbJEEAUCpmWkrN")

# # Initialize the Live client
# client = db.Live(API_KEY)

# # def handle_message(msg: Metadata):
# #     print(f"Received message: {msg}")

# # def handle_symbol_mapping(mapping: SymbolMapping):
# #     print(f"Symbol mapping: {mapping}")

# try:
#     # Subscribe to live snapshot
#     client.subscribe(
#         dataset="GLBX.MDP3",
#         schema="mbo",
#         symbols="ES.c.0",
#         stype_in="continuous",
#         snapshot=True,
#     )

#     # Set up message and symbol mapping handlers
#     client.on_message(handle_message)
#     client.on_symbol_mapping(handle_symbol_mapping)

#     print("Subscription started. Waiting for messages...")
    
#     # Start receiving messages
#     client.start()

# except Exception as e:
#     print(f"An error occurred with the live subscription: {e}")

# except KeyboardInterrupt:
#     print("Subscription stopped by user.")

# finally:
#     # Always close the client to release resources
#     client.close()


import os
import databento as db

# Replace with your Databento API key
API_KEY = "db-aPX3iuLkKyURgLvEbJEEAUCpmWkrN"

# Initialize the Live client
client = db.Live(API_KEY)

def handle_message(msg):
    print(f"Received message: {msg}")

def handle_symbol_mapping(mapping):
    print(f"Symbol mapping: {mapping}")

try:
    # Subscribe to live snapshot
    client.subscribe(
        dataset="GLBX.MDP3",
        schema="mbo",
        symbols="ES.c.0",
        stype_in="continuous",
        snapshot=True,
        handler=handle_message  # Pass the handler function directly here
    )

    print("Subscription started. Waiting for messages...")
    
    # Start receiving messages
    client.start()

except Exception as e:
    print(f"An error occurred with the live subscription: {e}")
except KeyboardInterrupt:
    print("Subscription stopped by user.")
finally:
    client.stop()