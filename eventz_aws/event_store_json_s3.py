from typing import Sequence, Tuple

import boto3
import botocore
from botocore.config import Config
from botocore.exceptions import ClientError
from eventz.event_store import EventStore
from eventz.messages import Event
from eventz.protocols import MarshallProtocol, EventStoreProtocol


class EventStoreJsonS3(EventStore, EventStoreProtocol):
    def __init__(
        self,
        bucket_name: str,
        region: str,
        marshall: MarshallProtocol,
        recreate_storage: bool = True,
    ):
        self._bucket_name: str = bucket_name
        client_config = Config(region_name=region,)
        self._resource = boto3.resource("s3", region_name=region, config=client_config,)
        self._client = boto3.client("s3", region_name=region, config=client_config,)
        self._marshall = marshall
        bucket_exists = self._bucket_exists()
        if not bucket_exists:
            self._resource.create_bucket(
                Bucket=self._bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        elif bucket_exists and recreate_storage:
            bucket = self._resource.Bucket(self._bucket_name)
            bucket.objects.all().delete()
            bucket.delete()
            self._resource.create_bucket(
                Bucket=self._bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )

    def fetch(self, aggregate_id: str) -> Tuple[Event, ...]:
        try:
            obj = self._client.get_object(Bucket=self._bucket_name, Key=aggregate_id)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return ()
            raise e
        json_string = obj.get("Body").read().decode("utf-8")
        return tuple(self._marshall.from_json(json_string))

    def persist(self, aggregate_id: str, events: Sequence[Event]) -> None:
        json_string = self._marshall.to_json(events)
        self._client.put_object(
            Bucket=self._bucket_name, Key=aggregate_id, Body=json_string
        )

    def _bucket_exists(self) -> bool:
        try:
            self._resource.meta.client.head_bucket(Bucket=self._bucket_name)
            return True
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] != "404":
                raise e
            return False
