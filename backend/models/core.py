from sqlalchemy import Column, String, Text, ForeignKey, Table, DateTime, Float
from sqlalchemy.orm import relationship
from backend.database import Base


class Employee(Base):
    """Employee record model."""
    __tablename__ = "employees"

    id = Column(String(50), primary_key=True)  # e.g., "E001"
    name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<Employee(id='{self.id}', name='{self.name}', role='{self.role}')>"


class Service(Base):
    """System service record model."""
    __tablename__ = "services"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    modules = relationship("Module", back_populates="service", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Service(id='{self.id}', name='{self.name}')>"

module_capabilities = Table(
    "module_capabilities",
    Base.metadata,
    Column("module_id", String(50), ForeignKey("modules.id"), primary_key=True),
    Column("capability_id", String(50), ForeignKey("capabilities.id"), primary_key=True),
)


class Module(Base):
    """System module record model."""
    __tablename__ = "modules"

    id = Column(String(50), primary_key=True)
    service_id = Column(String(50), ForeignKey("services.id"), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    service = relationship("Service", back_populates="modules")
    capabilities = relationship(
        "Capability",
        secondary=module_capabilities,
        back_populates="modules",
    )

    def __repr__(self):
        return f"<Module(id='{self.id}', name='{self.name}')>"


class Capability(Base):
    """Technical capability record model."""
    __tablename__ = "capabilities"

    id = Column(String(50), primary_key=True)  # e.g., "C001"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    modules = relationship(
        "Module",
        secondary=module_capabilities,
        back_populates="capabilities",
    )

    def __repr__(self):
        return f"<Capability(id='{self.id}', name='{self.name}')>"


# ... (Employee, Service, Module, Capability, module_capabilities as before) ...

class EvidenceRecord(Base):
    """A single piece of evidence linking an employee to a capability."""
    __tablename__ = "evidence_records"

    id = Column(String(50), primary_key=True)  # e.g. "EV0001"
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False)
    capability_id = Column(String(50), ForeignKey("capabilities.id"), nullable=False)
    module_id = Column(String(50), ForeignKey("modules.id"), nullable=True)

    source = Column(String(30), nullable=False)       # "git_commit" | "jira_issue" | etc.
    source_ref = Column(String(100), nullable=False)  # commit_id or jira_id
    event_date = Column(DateTime(timezone=True), nullable=False)
    weight = Column(Float, nullable=False, default=1.0)  # base weight before recency decay

    employee = relationship("Employee")
    capability = relationship("Capability")
    module = relationship("Module")

    def __repr__(self):
        return f"<EvidenceRecord(source='{self.source}', ref='{self.source_ref}')>"


class CapabilityScore(Base):
    """Aggregated, recency-decayed score per employee per capability."""
    __tablename__ = "capability_scores"

    employee_id = Column(String(50), ForeignKey("employees.id"), primary_key=True)
    capability_id = Column(String(50), ForeignKey("capabilities.id"), primary_key=True)
    score = Column(Float, nullable=False, default=0.0)
    evidence_count = Column(Float, nullable=False, default=0)

    employee = relationship("Employee")
    capability = relationship("Capability")

    def __repr__(self):
        return f"<CapabilityScore(employee='{self.employee_id}', capability='{self.capability_id}', score={self.score})>"
