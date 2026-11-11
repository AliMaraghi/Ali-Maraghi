"""Explicit caller-attested private import review; never OAuth consent itself."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportPolicy:
    owner_email: str
    allowed_services: frozenset
    review_reference: str
    retention_days: int
    mixed_content_reviewed: bool = False

    def require(self,owner,service):
        if (self.mixed_content_reviewed is not True or not isinstance(self.owner_email,str)
                or self.owner_email != owner or type(self.allowed_services) is not frozenset
                or service not in self.allowed_services or not isinstance(self.review_reference,str)
                or not 1<=len(self.review_reference)<=128
                or not all(c.isalnum() or c in '-_.' for c in self.review_reference)
                or type(self.retention_days) is not int or not 1<=self.retention_days<=365):
            raise PermissionError('Explicit per-source private import review required')
