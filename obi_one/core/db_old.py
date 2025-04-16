from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

# Association table for many-to-many relationship
circuit_collection_association = Table(
    'circuit_collection_association', Base.metadata,
    Column('collection_id', Integer, ForeignKey('circuit_collections.id')),
    Column('circuit_id', Integer, ForeignKey('circuits.id'))
)

class CircuitEntity(Base):
    __tablename__ = 'circuits'

    id = Column(Integer, primary_key=True)
    config_path = Column(String, nullable=False)

    def __repr__(self):
        return f"<CircuitEntity(id={self.id}, config_path='{self.config_path}')>"

def SaveCircuitEntity(config_path: str):

    circuit_entity = CircuitEntity(config_path=config_path)
    session.add(circuit_entity)
    session.commit()

    return circuit_entity


class CircuitCollectionEntity(Base):
    __tablename__ = 'circuit_collections'

    id = Column(Integer, primary_key=True)
    # name = Column(String, nullable=False)

    # Link to many circuits
    circuits = relationship(
        "CircuitEntity",
        secondary=circuit_collection_association,
        backref="collections"
    )

    def __repr__(self):
        return f"<CircuitCollectionEntity(id={self.id}')>" # , name='{self.name}


def SaveCircuitCollectionEntity(circuits: list[CircuitEntity]):

    collection = CircuitCollectionEntity(circuits=circuits)
    session.add(collection)
    session.commit()

import os
session = None
def database(db_path='sqlite:///obi.db'):

    # Setup SQLite in-memory database for simplicity
    engine = create_engine(db_path, echo=True)
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    global session
    session = Session()





# def create_circuits_and_collection(session, circuit_paths):
#     circuits = []
#     for circuit_path in circuit_paths:
#         circuit = CircuitEntity(config_path=circuit_path)
#         session.add(circuit)



#         circuits.append(circuit)
#     session.commit()

#     collection1 = CircuitCollectionEntity(name="First Collection", circuits=circuits)
#     session.add(collection1)
#     session.commit()


def circuit_collections():
    collections = session.query(CircuitCollectionEntity).all()
    print(collections)

def circuits():
    circuits = session.query(CircuitEntity).all()
    print(circuits)


def close_db():
    session.close()