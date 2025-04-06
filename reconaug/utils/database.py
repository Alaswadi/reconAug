from datetime import datetime
from reconaug import db
from reconaug.models import Scan, Subdomain, LiveHost, Port, HistoricalUrl

def save_scan_to_database(domain, subdomains, live_hosts, historical_urls=None):
    """Save scan results to the database"""
    try:
        print(f"Starting database save for domain: {domain}")
        
        # Create a new scan record
        scan = Scan(
            domain=domain,
            timestamp=datetime.utcnow(),
            status='complete',
            subdomains_count=len(subdomains),
            live_hosts_count=len(live_hosts)
        )
        db.session.add(scan)
        db.session.flush()  # Get the scan ID without committing
        print(f"Created scan record with ID: {scan.id}")
        
        # Add subdomains
        print(f"Adding {len(subdomains)} subdomains to database")
        for subdomain in subdomains:
            db.session.add(Subdomain(
                scan_id=scan.id,
                name=subdomain,
                source='combined'  # We don't track individual sources in this version
            ))
        
        # Add live hosts
        print(f"Adding {len(live_hosts)} live hosts to database")
        for host in live_hosts:
            try:
                live_host = LiveHost(
                    scan_id=scan.id,
                    url=host['url'],
                    status_code=host['status_code'],
                    technology=host['technology']
                )
                db.session.add(live_host)
                db.session.flush()  # Get the live host ID
            except KeyError as ke:
                print(f"KeyError in live host data: {ke}. Host data: {host}")
                # Continue with other hosts even if one fails
                continue
        
        # Add historical URLs if available
        if historical_urls:
            print(f"Adding {len(historical_urls)} historical URLs to database")
            for url in historical_urls:
                db.session.add(HistoricalUrl(
                    scan_id=scan.id,
                    url=url
                ))
        
        # Commit all changes
        db.session.commit()
        print(f"Scan results for {domain} saved to database successfully")
        return scan.id
    except Exception as e:
        db.session.rollback()
        print(f"Error saving scan results to database: {e}")
        import traceback
        traceback.print_exc()
        return None

def save_ports_to_database(host_url, ports):
    """Save port scan results to the database"""
    try:
        # Find the live host record
        host = LiveHost.query.filter_by(url=host_url).first()
        if not host:
            print(f"Live host {host_url} not found in database")
            return False
        
        # Add ports
        for port in ports:
            db.session.add(Port(
                host_id=host.id,
                port_number=port,
                service=get_common_service(port)
            ))
        
        # Commit changes
        db.session.commit()
        print(f"Port scan results for {host_url} saved to database")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error saving port scan results to database: {e}")
        return False

def get_common_service(port):
    """Return common service name for a port number"""
    common_ports = {
        21: 'FTP',
        22: 'SSH',
        23: 'Telnet',
        25: 'SMTP',
        53: 'DNS',
        80: 'HTTP',
        110: 'POP3',
        143: 'IMAP',
        443: 'HTTPS',
        445: 'SMB',
        3306: 'MySQL',
        3389: 'RDP',
        5432: 'PostgreSQL',
        8080: 'HTTP-Proxy',
        8443: 'HTTPS-Alt'
    }
    return common_ports.get(port, 'Unknown')
