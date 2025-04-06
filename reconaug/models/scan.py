from datetime import datetime
from reconaug import db

class Scan(db.Model):
    """Main scan information"""
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='complete')
    subdomains_count = db.Column(db.Integer, default=0)
    live_hosts_count = db.Column(db.Integer, default=0)
    
    # Relationships
    subdomains = db.relationship('Subdomain', backref='scan', lazy=True, cascade='all, delete-orphan')
    live_hosts = db.relationship('LiveHost', backref='scan', lazy=True, cascade='all, delete-orphan')
    historical_urls = db.relationship('HistoricalUrl', backref='scan', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Scan {self.domain} at {self.timestamp}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'domain': self.domain,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status,
            'subdomains_count': self.subdomains_count,
            'live_hosts_count': self.live_hosts_count
        }

class Subdomain(db.Model):
    """Subdomain information"""
    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey('scan.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    source = db.Column(db.String(50))  # subfinder, crtsh, chaos, sublist3r
    
    def __repr__(self):
        return f'<Subdomain {self.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'scan_id': self.scan_id,
            'name': self.name,
            'source': self.source
        }

class LiveHost(db.Model):
    """Live host information"""
    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey('scan.id'), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    status_code = db.Column(db.String(10))
    technology = db.Column(db.Text)
    
    # Relationships
    ports = db.relationship('Port', backref='host', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<LiveHost {self.url}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'scan_id': self.scan_id,
            'url': self.url,
            'status_code': self.status_code,
            'technology': self.technology
        }

class Port(db.Model):
    """Port information"""
    id = db.Column(db.Integer, primary_key=True)
    host_id = db.Column(db.Integer, db.ForeignKey('live_host.id'), nullable=False)
    port_number = db.Column(db.Integer, nullable=False)
    service = db.Column(db.String(50))
    
    def __repr__(self):
        return f'<Port {self.port_number}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'host_id': self.host_id,
            'port_number': self.port_number,
            'service': self.service
        }

class HistoricalUrl(db.Model):
    """Historical URL information from GAU"""
    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey('scan.id'), nullable=False)
    url = db.Column(db.Text, nullable=False)
    
    def __repr__(self):
        return f'<HistoricalUrl {self.url[:50]}...>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'scan_id': self.scan_id,
            'url': self.url
        }
