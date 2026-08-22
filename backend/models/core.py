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


class Module(Base):
    """System module record model."""
    __tablename__ = "modules"

    id = Column(String(50), primary_key=True)
    service_id = Column(String(50), ForeignKey("services.id"), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    service = relationship("Service", back_populates="modules")

    def __repr__(self):
        return f"<Module(id='{self.id}', name='{self.name}')>"


class Capability(Base):
    """Technical capability record model."""
    __tablename__ = "capabilities"

    id = Column(String(50), primary_key=True)  # e.g., "C001"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Capability(id='{self.id}', name='{self.name}')>"
