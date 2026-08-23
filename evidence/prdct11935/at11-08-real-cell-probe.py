"""Feed a REAL AWS cell's rendered config.yaml (c03/saas, head chart) to the config model and the
service's own branch selectors. If the head chart broke an AWS cell, it breaks here."""
import re, yaml
from common_core.config import CloudProvider
from endpoint_asset_ingestion.config import EndpointAssetIngestionConfig
from endpoint_asset_ingestion.consumer.event_parser import empty_parse_is_poison, parse_object_created_message, parser_for_cloud

raw = open('/tmp/prdct11935/r45/aws-cell-config.yaml').read()
subs = {  # the terraform-substituted values a real c03/saas cell supplies
    'region': 'us-east-1',
    'endpoint_asset_ingestion_queue_url': 'https://sqs.us-east-1.amazonaws.com/1234/endpoint-asset-ingestion',
    'endpoint_asset_ingestion_dlq_url': 'https://sqs.us-east-1.amazonaws.com/1234/endpoint-asset-ingestion-dlq',
    'alert_processing_queue_url': 'https://sqs.us-east-1.amazonaws.com/1234/alert-processing',
    'rds_endpoint': 'db.internal', 'temporal_namespace': 'saas',
    'releases_kvs_arn': '', 'releases_kvs_writer_role_arn': '',
}
def sub(m):
    key = m.group(1).split(':=')[0]
    return subs.get(key, '')
data = yaml.safe_load(re.sub(r'\$\{([^}]*)\}', sub, raw))
cfg = EndpointAssetIngestionConfig(**data)
print(f"  the rendered AWS-cell config CONSTRUCTS on the head model: cloud={cfg.cloud.value}")
print(f"    asset_ingestion_sqs.queue_url = {cfg.asset_ingestion_sqs.queue_url}")
print(f"    asset_ingestion_asb           = ns={cfg.asset_ingestion_asb.fully_qualified_namespace!r} queue={cfg.asset_ingestion_asb.queue_name!r}  (empty -> the transport guard is satisfied)")
print(f"    alert_processing_sqs.queue_url= {cfg.alert_processing_sqs.queue_url}")
print(f"    alert_processing_asb          = ns={cfg.alert_processing_asb.fully_qualified_namespace!r} queue={cfg.alert_processing_asb.queue_name!r}")
print(f"    s3 aws_region/endpoint        = {cfg.asset_ingestion_s3.aws_region!r} / {cfg.asset_ingestion_s3.endpoint!r}")
assert cfg.cloud is CloudProvider.AWS
print(f"  and the branch selectors it drives resolve to the AWS lane:")
print(f"    parser_for_cloud(cfg.cloud) is parse_object_created_message : {parser_for_cloud(cfg.cloud) is parse_object_created_message}")
print(f"    empty_parse_is_poison(cfg.cloud)                            : {empty_parse_is_poison(cfg.cloud)}")
print(f"    alert fan-out arm taken                                     : {'sqs' if (cfg.cloud is not CloudProvider.AZURE and cfg.alert_processing_sqs.queue_url) else 'other'}")
