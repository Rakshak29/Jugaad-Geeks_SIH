from sqlalchemy import Column, String, Text, ForeignKey
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
