from datetime import datetime
from reconaug import create_app
from reconaug.models import Scan, Subdomain, LiveHost, Port, HistoricalUrl

def save_scan_results(domain, subdomains, live_hosts):
    """Save scan results to the database using a new app context"""
    try:
        # Create a new Flask app and context
        app = create_app()
        with app.app_context():
            from reconaug import db

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

            # Commit all changes
            db.session.commit()
            print(f"Scan results for {domain} saved to database successfully")
            return scan.id
    except Exception as e:
        print(f"Error saving scan results to database: {e}")
        import traceback
        traceback.print_exc()
        return None

def save_port_scan_results(host_url, ports):
    """Save port scan results to the database using a new app context"""
    try:
        # Create a new Flask app and context
        app = create_app()
        with app.app_context():
            from reconaug import db

            # Find the live host record
            host = LiveHost.query.filter_by(url=host_url).first()

            # If host not found, try to create it
            if not host:
                print(f"Live host {host_url} not found in database, creating new entry")

                # Extract domain from URL
                domain = host_url
                if '://' in host_url:
                    domain = host_url.split('://', 1)[1].split('/', 1)[0]
                if ':' in domain:
                    domain = domain.split(':', 1)[0]

                # Find the most recent scan for this domain
                scan = db.session.query(Scan).filter(Scan.domain.like(f'%{domain}%')).order_by(Scan.timestamp.desc()).first()

                if not scan:
                    print(f"No scan found for domain {domain}, creating new scan record")
                    scan = Scan(
                        domain=domain,
                        timestamp=datetime.utcnow(),
                        status='complete',
                        subdomains_count=0,
                        live_hosts_count=1
                    )
                    db.session.add(scan)
                    db.session.flush()  # Get the scan ID without committing

                # Create new live host record
                host = LiveHost(
                    scan_id=scan.id,
                    url=host_url,
                    status_code='200',  # Default status code
                    technology='Unknown'
                )
                db.session.add(host)
                db.session.flush()  # Get the host ID without committing
                print(f"Created new live host record with ID: {host.id}")

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
        print(f"Error saving port scan results to database: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_historical_urls(domain, urls):
    """Save historical URLs to the database using a new app context"""
    try:
        # Create a new Flask app and context
        app = create_app()
        with app.app_context():
            from reconaug import db

            print(f"Saving historical URLs for domain: {domain}")

            # Find the most recent scan for this domain
            from reconaug.models import Scan
            scan = db.session.query(Scan).filter_by(domain=domain).order_by(Scan.timestamp.desc()).first()

            # If no scan found, try with/without www prefix
            if not scan and domain.startswith('www.'):
                base_domain = domain[4:]
                scan = db.session.query(Scan).filter_by(domain=base_domain).order_by(Scan.timestamp.desc()).first()
            if not scan and not domain.startswith('www.'):
                www_domain = f"www.{domain}"
                scan = db.session.query(Scan).filter_by(domain=www_domain).order_by(Scan.timestamp.desc()).first()

            # If still no scan found, create a new one
            if not scan:
                print(f"No existing scan found for {domain}, creating new scan record")
                scan = Scan(
                    domain=domain,
                    timestamp=datetime.utcnow(),
                    status='complete',
                    subdomains_count=0,
                    live_hosts_count=0
                )
                db.session.add(scan)
                db.session.flush()  # Get the scan ID without committing

            print(f"Using scan ID: {scan.id} for historical URLs")

            # Check if we already have historical URLs for this scan
            existing_count = db.session.query(HistoricalUrl).filter_by(scan_id=scan.id).count()
            if existing_count > 0:
                print(f"Found {existing_count} existing historical URLs for scan ID: {scan.id}, deleting them")
                db.session.query(HistoricalUrl).filter_by(scan_id=scan.id).delete()

            # Add historical URLs
            print(f"Adding {len(urls)} historical URLs to database")
            batch_size = 100
            for i in range(0, len(urls), batch_size):
                batch = urls[i:i+batch_size]
                for url in batch:
                    if isinstance(url, str):
                        db.session.add(HistoricalUrl(
                            scan_id=scan.id,
                            url=url
                        ))
                db.session.flush()

            # Commit all changes
            db.session.commit()
            print(f"Historical URLs for {domain} saved to database successfully")
            return scan.id
    except Exception as e:
        print(f"Error saving historical URLs to database: {e}")
        import traceback
        traceback.print_exc()
        return None

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
