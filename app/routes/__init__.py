from .url_shortener import url_bp

def register_routes(app):
    """Register all route blueprints with the Flask app."""
    # This 'plugs in' your URL shortener logic
    app.register_blueprint(url_bp)