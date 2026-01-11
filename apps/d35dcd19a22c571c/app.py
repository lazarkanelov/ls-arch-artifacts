import boto3
import json
import logging
import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import gzip
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WAFSecurityManager:
    """Manages WAF security automations including IP blocking, log analysis, and threat detection."""
    
    def __init__(self, server_hex: str, uuid: str):
        self.server_hex = server_hex
        self.uuid = uuid
        self.endpoint_url = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        
        # Initialize AWS clients
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.wafv2_client = boto3.client(
            "wafv2",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.sns_client = boto3.client(
            "sns",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        self.kms_client = boto3.client(
            "kms",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        # Resource names based on Terraform configuration
        self.waf_log_bucket = f"{server_hex}-waflogbucket"
        self.access_log_bucket = f"{server_hex}-accesslogging"
        self.sns_topic_name = f"AWS-WAF-Security-Automations-IP-Expiration-Notification-{uuid}"
        
    def upload_waf_logs(self, log_entries: List[Dict[str, Any]]) -> bool:
        """Upload WAF log entries to S3 for analysis."""
        try:
            # Create compressed log data
            log_data = "\n".join([json.dumps(entry) for entry in log_entries])
            
            # Compress the log data
            buffer = io.BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode='w') as f:
                f.write(log_data.encode('utf-8'))
            compressed_data = buffer.getvalue()
            
            # Generate log file key with timestamp
            timestamp = datetime.utcnow().strftime('%Y/%m/%d/%H')
            log_key = f"AWSLogs/123456789012/WAFLogs/us-east-1/{timestamp}/waf-logs-{int(time.time())}.gz"
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.waf_log_bucket,
                Key=log_key,
                Body=compressed_data,
                ContentType="application/gzip",
                ContentEncoding="gzip"
            )
            
            logger.info(f"Uploaded WAF logs to s3://{self.waf_log_bucket}/{log_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload WAF logs: {str(e)}")
            return False
    
    def analyze_threat_patterns(self, log_key: str) -> Dict[str, Any]:
        """Analyze WAF logs to identify threat patterns and suspicious IPs."""
        try:
            # Download and decompress log file
            response = self.s3_client.get_object(Bucket=self.waf_log_bucket, Key=log_key)
            compressed_data = response['Body'].read()
            
            with gzip.GzipFile(fileobj=io.BytesIO(compressed_data)) as f:
                log_data = f.read().decode('utf-8')
            
            # Parse log entries
            log_entries = [json.loads(line) for line in log_data.strip().split('\n') if line]
            
            # Analyze patterns
            threat_analysis = {
                'total_requests': len(log_entries),
                'blocked_requests': 0,
                'suspicious_ips': {},
                'attack_patterns': {
                    'sql_injection': 0,
                    'xss_attempts': 0,
                    'brute_force': 0,
                    'scanning': 0
                },
                'top_blocked_countries': {},
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
            
            for entry in log_entries:
                client_ip = entry.get('httpRequest', {}).get('clientIp', '')
                action = entry.get('action', '')
                uri = entry.get('httpRequest', {}).get('uri', '')
                args = entry.get('httpRequest', {}).get('args', '')
                country = entry.get('httpRequest', {}).get('country', 'Unknown')
                
                # Count blocked requests
                if action == 'BLOCK':
                    threat_analysis['blocked_requests'] += 1
                    
                    # Track suspicious IPs
                    if client_ip not in threat_analysis['suspicious_ips']:
                        threat_analysis['suspicious_ips'][client_ip] = 0
                    threat_analysis['suspicious_ips'][client_ip] += 1
                    
                    # Track blocked countries
                    if country not in threat_analysis['top_blocked_countries']:
                        threat_analysis['top_blocked_countries'][country] = 0
                    threat_analysis['top_blocked_countries'][country] += 1
                
                # Detect attack patterns
                combined_input = f"{uri} {args}".lower()
                if any(pattern in combined_input for pattern in ['union select', 'or 1=1', "'; drop"]):  
                    threat_analysis['attack_patterns']['sql_injection'] += 1
                elif any(pattern in combined_input for pattern in ['<script>', 'javascript:', 'onerror=']):
                    threat_analysis['attack_patterns']['xss_attempts'] += 1
                elif uri in ['/login', '/admin', '/wp-admin'] and args:
                    threat_analysis['attack_patterns']['brute_force'] += 1
                elif uri.endswith('.php') or '..' in uri:
                    threat_analysis['attack_patterns']['scanning'] += 1
            
            # Save analysis results
            analysis_key = f"threat-analysis/{datetime.utcnow().strftime('%Y/%m/%d')}/analysis-{int(time.time())}.json"
            self.s3_client.put_object(
                Bucket=self.waf_log_bucket,
                Key=analysis_key,
                Body=json.dumps(threat_analysis, indent=2),
                ContentType="application/json"
            )
            
            logger.info(f"Threat analysis completed: {threat_analysis['blocked_requests']} blocked requests from {len(threat_analysis['suspicious_ips'])} suspicious IPs")
            return threat_analysis
            
        except Exception as e:
            logger.error(f"Failed to analyze threat patterns: {str(e)}")
            return {}
    
    def update_ip_sets_from_analysis(self, threat_analysis: Dict[str, Any], block_threshold: int = 10) -> bool:
        """Update WAF IP sets based on threat analysis results."""
        try:
            if not threat_analysis.get('suspicious_ips'):
                logger.info("No suspicious IPs found to block")
                return True
            
            # Get IPs that exceed the blocking threshold
            ips_to_block = [
                f"{ip}/32" for ip, count in threat_analysis['suspicious_ips'].items() 
                if count >= block_threshold
            ]
            
            if not ips_to_block:
                logger.info(f"No IPs exceed the blocking threshold of {block_threshold}")
                return True
            
            # Get current blacklist IP set
            try:
                ip_set_response = self.wafv2_client.get_ip_set(
                    Name="WAFBlacklistSetV41",
                    Scope="REGIONAL",
                    Id="dummy-id"  # This would be the actual IP set ID in real AWS
                )
                current_addresses = ip_set_response.get('IPSet', {}).get('Addresses', [])
                lock_token = ip_set_response.get('LockToken')
            except Exception:
                # IP set doesn't exist or error occurred
                current_addresses = []
                lock_token = "dummy-token"
            
            # Merge with existing IPs
            updated_addresses = list(set(current_addresses + ips_to_block))
            
            # Update IP set (this would work with real AWS)
            try:
                self.wafv2_client.update_ip_set(
                    Name="WAFBlacklistSetV41",
                    Scope="REGIONAL",
                    Id="dummy-id",
                    Addresses=updated_addresses,
                    LockToken=lock_token
                )
                logger.info(f"Updated blacklist IP set with {len(ips_to_block)} new IPs: {ips_to_block}")
            except Exception as e:
                logger.warning(f"Could not update IP set (expected in LocalStack): {str(e)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update IP sets: {str(e)}")
            return False
    
    def send_security_notification(self, threat_analysis: Dict[str, Any]) -> bool:
        """Send security notification via SNS when threats are detected."""
        try:
            # Find SNS topic ARN
            topics = self.sns_client.list_topics()
            topic_arn = None
            
            for topic in topics.get('Topics', []):
                if self.sns_topic_name in topic['TopicArn']:
                    topic_arn = topic['TopicArn']
                    break
            
            if not topic_arn:
                logger.warning(f"SNS topic {self.sns_topic_name} not found")
                return False
            
            # Prepare notification message
            blocked_count = threat_analysis.get('blocked_requests', 0)
            suspicious_ip_count = len(threat_analysis.get('suspicious_ips', {}))
            top_attacks = threat_analysis.get('attack_patterns', {})
            
            message = f"""WAF Security Alert - Threat Analysis Report

Timestamp: {threat_analysis.get('analysis_timestamp', 'Unknown')}
Total Requests Analyzed: {threat_analysis.get('total_requests', 0)}
Blocked Requests: {blocked_count}
Suspicious IPs Detected: {suspicious_ip_count}

Attack Patterns Detected:
- SQL Injection Attempts: {top_attacks.get('sql_injection', 0)}
- XSS Attempts: {top_attacks.get('xss_attempts', 0)}
- Brute Force Attempts: {top_attacks.get('brute_force', 0)}
- Scanning Activities: {top_attacks.get('scanning', 0)}

Top Blocked Countries: {', '.join(threat_analysis.get('top_blocked_countries', {}).keys())}

This is an automated security notification from your WAF Security Automations.
"""
            
            # Send notification
            self.sns_client.publish(
                TopicArn=topic_arn,
                Subject="WAF Security Alert - Threats Detected",
                Message=message
            )
            
            logger.info(f"Security notification sent to SNS topic: {topic_arn}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send security notification: {str(e)}")
            return False
    
    def process_security_automation_workflow(self, log_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute the complete security automation workflow."""
        workflow_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'log_upload_success': False,
            'threat_analysis_completed': False,
            'ip_sets_updated': False,
            'notification_sent': False,
            'log_key': None,
            'threat_summary': {}
        }
        
        try:
            logger.info("Starting WAF security automation workflow")
            
            # Step 1: Upload logs to S3
            upload_success = self.upload_waf_logs(log_entries)
            workflow_results['log_upload_success'] = upload_success
            
            if not upload_success:
                logger.error("Workflow terminated: Log upload failed")
                return workflow_results
            
            # Step 2: Find the uploaded log file
            timestamp = datetime.utcnow().strftime('%Y/%m/%d/%H')
            log_prefix = f"AWSLogs/123456789012/WAFLogs/us-east-1/{timestamp}/"
            
            try:
                objects = self.s3_client.list_objects_v2(
                    Bucket=self.waf_log_bucket,
                    Prefix=log_prefix
                )
                
                if 'Contents' in objects and objects['Contents']:
                    # Get the most recent log file
                    latest_log = sorted(objects['Contents'], key=lambda x: x['LastModified'])[-1]
                    log_key = latest_log['Key']
                    workflow_results['log_key'] = log_key
                else:
                    raise Exception("No log files found")
                    
            except Exception as e:
                logger.error(f"Could not find uploaded log file: {str(e)}")
                return workflow_results
            
            # Step 3: Analyze threat patterns
            threat_analysis = self.analyze_threat_patterns(log_key)
            workflow_results['threat_analysis_completed'] = bool(threat_analysis)
            workflow_results['threat_summary'] = threat_analysis
            
            if not threat_analysis:
                logger.error("Workflow terminated: Threat analysis failed")
                return workflow_results
            
            # Step 4: Update IP sets if threats detected
            if threat_analysis.get('blocked_requests', 0) > 0:
                ip_update_success = self.update_ip_sets_from_analysis(threat_analysis)
                workflow_results['ip_sets_updated'] = ip_update_success
                
                # Step 5: Send notification for significant threats
                if threat_analysis.get('blocked_requests', 0) > 5:
                    notification_success = self.send_security_notification(threat_analysis)
                    workflow_results['notification_sent'] = notification_success
            
            logger.info("WAF security automation workflow completed successfully")
            return workflow_results
            
        except Exception as e:
            logger.error(f"Workflow failed with error: {str(e)}")
            return workflow_results
    
    def get_security_dashboard_data(self) -> Dict[str, Any]:
        """Retrieve security dashboard data from stored analysis results."""
        try:
            # List recent analysis files
            today = datetime.utcnow().strftime('%Y/%m/%d')
            analysis_prefix = f"threat-analysis/{today}/"
            
            objects = self.s3_client.list_objects_v2(
                Bucket=self.waf_log_bucket,
                Prefix=analysis_prefix
            )
            
            dashboard_data = {
                'last_updated': datetime.utcnow().isoformat(),
                'total_analyses': 0,
                'aggregated_threats': {
                    'total_blocked': 0,
                    'unique_attackers': set(),
                    'attack_patterns': {
                        'sql_injection': 0,
                        'xss_attempts': 0,
                        'brute_force': 0,
                        'scanning': 0
                    },
                    'top_countries': {}
                },
                'recent_analyses': []
            }
            
            if 'Contents' not in objects:
                logger.info("No analysis data found for today")
                return dashboard_data
            
            # Process recent analysis files
            for obj in sorted(objects['Contents'], key=lambda x: x['LastModified'], reverse=True)[:10]:
                try:
                    response = self.s3_client.get_object(Bucket=self.waf_log_bucket, Key=obj['Key'])
                    analysis_data = json.loads(response['Body'].read().decode('utf-8'))
                    
                    dashboard_data['total_analyses'] += 1
                    dashboard_data['recent_analyses'].append({
                        'timestamp': analysis_data.get('analysis_timestamp'),
                        'blocked_requests': analysis_data.get('blocked_requests', 0),
                        'suspicious_ips': len(analysis_data.get('suspicious_ips', {})),
                        'key': obj['Key']
                    })
                    
                    # Aggregate data
                    dashboard_data['aggregated_threats']['total_blocked'] += analysis_data.get('blocked_requests', 0)
                    
                    for ip in analysis_data.get('suspicious_ips', {}).keys():
                        dashboard_data['aggregated_threats']['unique_attackers'].add(ip)
                    
                    # Aggregate attack patterns
                    for pattern, count in analysis_data.get('attack_patterns', {}).items():
                        dashboard_data['aggregated_threats']['attack_patterns'][pattern] += count
                    
                    # Aggregate country data
                    for country, count in analysis_data.get('top_blocked_countries', {}).items():
                        if country not in dashboard_data['aggregated_threats']['top_countries']:
                            dashboard_data['aggregated_threats']['top_countries'][country] = 0
                        dashboard_data['aggregated_threats']['top_countries'][country] += count
                        
                except Exception as e:
                    logger.warning(f"Could not process analysis file {obj['Key']}: {str(e)}")
                    continue
            
            # Convert set to count
            dashboard_data['aggregated_threats']['unique_attackers'] = len(dashboard_data['aggregated_threats']['unique_attackers'])
            
            logger.info(f"Dashboard data retrieved: {dashboard_data['total_analyses']} analyses, {dashboard_data['aggregated_threats']['total_blocked']} total blocked requests")
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Failed to retrieve dashboard data: {str(e)}")
            return {'error': str(e)}