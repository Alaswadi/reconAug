import os
from reconaug import create_app

# Create output directory if it doesn't exist
os.makedirs('output', exist_ok=True)

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
