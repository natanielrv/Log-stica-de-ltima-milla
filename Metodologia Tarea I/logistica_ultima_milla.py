#!/usr/bin/env python3
"""
=============================================================================
Sistema de Logística de Última Milla
Entregable 1 - Arquitectura de Software 2
=============================================================================
CASOS DE USO:
  1. Gestión de Pedidos       (Crear, Validar, Gestionar estados)
  2. Monitoreo y Tracking     (Visualizar, Notificar, Registrar eventos)
  3. Gestión de Repartidores  (Registrar, Disponibilidad, Asignar, Ubicación)
  4. Gestión de Rutas         (Definir, Ajustar dinámicamente, Seguimiento)

SOLID:
  S - Single Responsibility: cada clase tiene una sola responsabilidad
  O - Open/Closed: nuevos canales = nueva subclase, sin modificar existentes
  L - Liskov: PropioChannel y EcommerceChannel son intercambiables
  I - Interface Segregation: INotifiable, IAddressAdapter son interfaces mínimas
  D - Dependency Inversion: LogisticsFacade recibe dependencias por constructor

PATRONES:
  Creacionales : Factory Method, Abstract Factory, Builder, Singleton
  Estructurales: Adapter, Decorator, Facade
=============================================================================
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import random
import datetime

# ===========================================================================
# DOMINIO
# ===========================================================================

class OrderStatus(Enum):
    CREADO               = "CREADO"
    VALIDADO             = "VALIDADO"
    PENDIENTE_ASIGNACION = "PENDIENTE_ASIGNACION"
    ASIGNADO             = "ASIGNADO"
    EN_RUTA              = "EN_RUTA"
    INTENTO_FALLIDO      = "INTENTO_FALLIDO"
    REPROGRAMADO         = "REPROGRAMADO"
    ENTREGADO            = "ENTREGADO"
    CANCELADO            = "CANCELADO"

class DeliveryType(Enum):
    NORMAL     = "NORMAL"
    EXPRESS    = "EXPRESS"
    PROGRAMADA = "PROGRAMADA"

class Channel(Enum):
    CANAL_PROPIO = "CANAL_PROPIO"
    ECOMMERCE    = "ECOMMERCE"

ROUTE_DOMAIN_MIN = 1
ROUTE_DOMAIN_MAX = 100

SEP  = "=" * 65
SEP2 = "-" * 65

# ===========================================================================
# ADAPTER - Convierte dict externo en Address del dominio
# SOLID D: el dominio depende de IAddressAdapter (abstracción)
# ===========================================================================

@dataclass(frozen=True)
class Address:
    street: str
    number: int
    city: str

    def is_valid(self) -> bool:
        # SOLID S: regla de validación en el propio Value Object
        return ROUTE_DOMAIN_MIN <= self.number <= ROUTE_DOMAIN_MAX

class IAddressAdapter(ABC):
    # SOLID I: interfaz mínima y segregada
    @abstractmethod
    def adapt(self, raw: dict) -> Address: ...

class ExternalAddressAdapter(IAddressAdapter):
    """[PATRON: ADAPTER] Traduce dict externo al Value Object Address."""
    def adapt(self, raw: dict) -> Address:
        try:
            number = int(raw.get("nro", -1))
        except (ValueError, TypeError):
            number = -1
        return Address(
            street=str(raw.get("calle", "")),
            number=number,
            city=str(raw.get("ciudad", "")),
        )

# ===========================================================================
# SINGLETON - EventLogger
# SOLID S: solo registra eventos
# ===========================================================================

class EventLogger:
    """[PATRON: SINGLETON] Una única instancia de logger en todo el sistema."""
    _instance: Optional[EventLogger] = None

    def __new__(cls) -> EventLogger:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._log: list[str] = []
        return cls._instance

    def log(self, message: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self._log.append(entry)
        print(f"  LOG: {entry}")

    def get_events(self) -> list[str]:
        return list(self._log)

# ===========================================================================
# BUILDER - OrderBuilder
# SOLID S: la construcción del pedido es responsabilidad del Builder
# ===========================================================================

@dataclass
class Order:
    """Entidad central: Pedido."""
    order_id: str
    channel: Channel
    origin: Optional[Address]           = None
    destination: Optional[Address]      = None
    recipient_name: str                 = ""
    contact_medium: str                 = ""
    delivery_type: Optional[DeliveryType] = None
    cargo_type: str                     = ""
    weight_kg: float                    = 0.0
    status: OrderStatus                 = OrderStatus.CREADO
    assigned_courier_id: Optional[int]  = None
    route_id: Optional[str]             = None
    events: list[str]                   = field(default_factory=list)

    def add_event(self, event: str) -> None:
        self.events.append(event)

class OrderBuilder:
    """[PATRON: BUILDER] Construye un Order paso a paso con API fluida."""
    def __init__(self, order_id: str, channel: Channel) -> None:
        self._order = Order(order_id=order_id, channel=channel)

    def set_origin(self, address: Address) -> "OrderBuilder":
        self._order.origin = address
        return self

    def set_destination(self, address: Address) -> "OrderBuilder":
        self._order.destination = address
        return self

    def set_recipient(self, name: str, contact: str) -> "OrderBuilder":
        self._order.recipient_name = name
        self._order.contact_medium = contact
        return self

    def set_delivery(self, delivery_type: DeliveryType) -> "OrderBuilder":
        self._order.delivery_type = delivery_type
        return self

    def set_cargo(self, cargo_type: str, weight_kg: float) -> "OrderBuilder":
        self._order.cargo_type = cargo_type
        self._order.weight_kg = weight_kg
        return self

    def build(self) -> Order:
        return self._order

# ===========================================================================
# FACTORY METHOD + ABSTRACT FACTORY
# SOLID O: nuevo canal = nueva subclase, sin modificar las existentes
# SOLID L: PropioChannel y EcommerceChannel son intercambiables
# ===========================================================================

class AbstractChannel(ABC):
    """[PATRON: FACTORY METHOD - Creador Abstracto]"""
    @abstractmethod
    def create_order(self, order_id: str, raw_origin: dict,
                     raw_destination: dict, recipient_name: str,
                     contact: str, delivery_type: DeliveryType,
                     cargo_type: str, weight_kg: float) -> Order: ...

class PropioChannel(AbstractChannel):
    """[PATRON: FACTORY METHOD - Creador Concreto] Canal propio."""
    def create_order(self, order_id, raw_origin, raw_destination,
                     recipient_name, contact, delivery_type, cargo_type, weight_kg):
        adapter = ExternalAddressAdapter()   # ADAPTER en uso
        return (OrderBuilder(order_id, Channel.CANAL_PROPIO)
                .set_origin(adapter.adapt(raw_origin))
                .set_destination(adapter.adapt(raw_destination))
                .set_recipient(recipient_name, contact)
                .set_delivery(delivery_type)
                .set_cargo(cargo_type, weight_kg)
                .build())

class EcommerceChannel(AbstractChannel):
    """[PATRON: FACTORY METHOD - Creador Concreto] Canal e-commerce."""
    def create_order(self, order_id, raw_origin, raw_destination,
                     recipient_name, contact, delivery_type, cargo_type, weight_kg):
        adapter = ExternalAddressAdapter()   # ADAPTER en uso
        return (OrderBuilder(order_id, Channel.ECOMMERCE)
                .set_origin(adapter.adapt(raw_origin))
                .set_destination(adapter.adapt(raw_destination))
                .set_recipient(recipient_name, contact)
                .set_delivery(delivery_type)
                .set_cargo(cargo_type, weight_kg)
                .build())

class INotifiable(ABC):
    """[PATRON: ABSTRACT FACTORY - Producto Abstracto] SOLID I: interfaz mínima."""
    @abstractmethod
    def notify(self, recipient: str, message: str) -> None: ...

class SmsNotifier(INotifiable):
    def notify(self, recipient: str, message: str) -> None:
        print(f"  SMS  -> {recipient}: {message}")

class EmailNotifier(INotifiable):
    def notify(self, recipient: str, message: str) -> None:
        print(f"  Email-> {recipient}: {message}")

class AbstractOrderFactory(ABC):
    """[PATRON: ABSTRACT FACTORY - Fabrica Abstracta]"""
    @abstractmethod
    def get_channel(self) -> AbstractChannel: ...
    @abstractmethod
    def get_notifier(self) -> INotifiable: ...

class PropioFactory(AbstractOrderFactory):
    """[PATRON: ABSTRACT FACTORY - Fabrica Concreta] Canal propio + SMS."""
    def get_channel(self) -> AbstractChannel: return PropioChannel()
    def get_notifier(self) -> INotifiable:    return SmsNotifier()

class EcommerceFactory(AbstractOrderFactory):
    """[PATRON: ABSTRACT FACTORY - Fabrica Concreta] E-commerce + Email."""
    def get_channel(self) -> AbstractChannel: return EcommerceChannel()
    def get_notifier(self) -> INotifiable:    return EmailNotifier()

# ===========================================================================
# DECORATOR - LoggingNotifierDecorator
# SOLID O: agrega logging sin modificar SmsNotifier/EmailNotifier
# ===========================================================================

class LoggingNotifierDecorator(INotifiable):
    """[PATRON: DECORATOR] Agrega logging automatico a cualquier notificador."""
    def __init__(self, wrapped: INotifiable) -> None:
        self._wrapped = wrapped
        self._logger  = EventLogger()  # SINGLETON

    def notify(self, recipient: str, message: str) -> None:
        self._wrapped.notify(recipient, message)
        self._logger.log(f"Notificacion enviada a '{recipient}': {message}")

# ===========================================================================
# VALIDACION DE PEDIDOS
# SOLID S: unica responsabilidad = validar
# ===========================================================================

class OrderValidator:
    """SOLID S: unica responsabilidad = validar pedidos."""
    def validate(self, order: Order) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not order.origin or not order.origin.is_valid():
            errors.append("Direccion de origen invalida o fuera del dominio [1-100].")
        if not order.destination or not order.destination.is_valid():
            errors.append("Direccion de destino invalida o fuera del dominio [1-100].")
        if not order.recipient_name:
            errors.append("Falta nombre del destinatario.")
        if not order.contact_medium:
            errors.append("Falta medio de contacto.")
        if not order.delivery_type:
            errors.append("Falta tipo de entrega.")
        if not order.cargo_type:
            errors.append("Falta tipo de carga.")
        if order.weight_kg <= 0:
            errors.append("Peso debe ser mayor a 0.")
        if not order.order_id or not order.channel:
            errors.append("Falta ID unico o canal de origen.")
        return (len(errors) == 0, errors)

# ===========================================================================
# GESTION DE ESTADOS
# SOLID S: unica responsabilidad = transiciones de estado
# ===========================================================================

class OrderStateManager:
    """SOLID S: unica responsabilidad = gestionar transiciones de estado."""
    _TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
        OrderStatus.CREADO:               [OrderStatus.VALIDADO, OrderStatus.CANCELADO],
        OrderStatus.VALIDADO:             [OrderStatus.PENDIENTE_ASIGNACION, OrderStatus.CANCELADO],
        OrderStatus.PENDIENTE_ASIGNACION: [OrderStatus.ASIGNADO, OrderStatus.CANCELADO],
        OrderStatus.ASIGNADO:             [OrderStatus.EN_RUTA, OrderStatus.PENDIENTE_ASIGNACION, OrderStatus.CANCELADO],
        OrderStatus.EN_RUTA:              [OrderStatus.ENTREGADO, OrderStatus.INTENTO_FALLIDO, OrderStatus.CANCELADO],
        OrderStatus.INTENTO_FALLIDO:      [OrderStatus.REPROGRAMADO, OrderStatus.CANCELADO],
        OrderStatus.REPROGRAMADO:         [OrderStatus.ASIGNADO, OrderStatus.CANCELADO],
        OrderStatus.ENTREGADO:            [],
        OrderStatus.CANCELADO:            [],
    }

    def transition(self, order: Order, new_status: OrderStatus) -> bool:
        allowed = self._TRANSITIONS.get(order.status, [])
        if new_status in allowed:
            order.status = new_status
            order.add_event(f"Estado -> {new_status.value}")
            EventLogger().log(f"Pedido {order.order_id}: {new_status.value}")
            return True
        EventLogger().log(
            f"Transicion invalida: {order.status.value} -> {new_status.value} "
            f"(pedido {order.order_id})"
        )
        return False

# ===========================================================================
# REPARTIDORES
# Volumen maximo de carga en m3 (no cantidad de pedidos)
# Puede manejar multiples pedidos mientras no supere su volumen maximo
# ===========================================================================

@dataclass
class Courier:
    """
    Entidad Repartidor.
    max_volume_m3 : volumen maximo que puede transportar (m3)
    current_volume: volumen actualmente ocupado
    location      : posicion en dominio [1..100]
    """
    courier_id: int
    name: str
    max_volume_m3: float
    available: bool           = True
    current_volume: float     = 0.0
    current_orders: list[str] = field(default_factory=list)
    location: int             = 50

    def can_accept(self, order_volume: float = 0.0) -> bool:
        return self.available and (self.current_volume + order_volume) <= self.max_volume_m3

    def assign_order(self, order_id: str, order_volume: float = 0.0) -> None:
        self.current_orders.append(order_id)
        self.current_volume += order_volume

    def update_location(self, loc: int) -> bool:
        if ROUTE_DOMAIN_MIN <= loc <= ROUTE_DOMAIN_MAX:
            self.location = loc
            return True
        return False

class CourierRepository:
    """SOLID S: CRUD de repartidores en memoria."""
    def __init__(self) -> None:
        self._couriers: dict[int, Courier] = {}
        self._next_id: int = 1

    def register(self, name: str, max_volume_m3: float) -> Courier:
        courier = Courier(courier_id=self._next_id, name=name, max_volume_m3=max_volume_m3)
        self._couriers[self._next_id] = courier
        self._next_id += 1
        EventLogger().log(f"Repartidor registrado: {name} (ID={courier.courier_id}, vol_max={max_volume_m3}m3)")
        return courier

    def get_available(self, order_volume: float = 0.0) -> list[Courier]:
        return [c for c in self._couriers.values() if c.can_accept(order_volume)]

    def get_by_id(self, courier_id: int) -> Optional[Courier]:
        return self._couriers.get(courier_id)

    def update_location(self, courier_id: int, location: int) -> bool:
        c = self.get_by_id(courier_id)
        if not c:
            print(f"  ERROR: Repartidor {courier_id} no existe.")
            return False
        ok = c.update_location(location)
        if ok:
            EventLogger().log(f"Repartidor {courier_id} ({c.name}) ubicacion -> {location}")
        else:
            print(f"  ERROR: Ubicacion {location} fuera del dominio [{ROUTE_DOMAIN_MIN}-{ROUTE_DOMAIN_MAX}].")
        return ok

    def set_availability(self, courier_id: int, available: bool) -> None:
        c = self.get_by_id(courier_id)
        if c:
            c.available = available
            estado = "disponible" if available else "no disponible"
            EventLogger().log(f"Repartidor {courier_id} ({c.name}) -> {estado}")

    def all(self) -> list[Courier]:
        return list(self._couriers.values())

# ===========================================================================
# RUTAS
# Ajuste dinamico: agrega pedido y reordena por numero de destino
# Score aleatorio como heuristica de mejor ruta
# ===========================================================================

@dataclass
class Route:
    route_id: str
    order_ids: list[str]    = field(default_factory=list)
    best_score: int         = 0
    active: bool            = True
    tracking_log: list[str] = field(default_factory=list)

class RouteManager:
    """SOLID S: unica responsabilidad = gestion de rutas."""
    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}
        self._next_id: int = 1

    def define_route(self, order_ids: list[str]) -> Route:
        route_id = f"RUTA-{self._next_id:03d}"
        score    = random.randint(ROUTE_DOMAIN_MIN, ROUTE_DOMAIN_MAX)
        route    = Route(route_id=route_id, order_ids=list(order_ids), best_score=score)
        self._routes[route_id] = route
        self._next_id += 1
        EventLogger().log(f"Ruta definida: {route_id} | pedidos={order_ids} | score={score}")
        return route

    def adjust_route(self, route_id: str, new_order_id: str,
                     order_repo: "OrderRepository") -> bool:
        """
        Ajuste dinamico: agrega pedido a ruta activa y reordena por destino.
        Simula optimizacion de recorrido dentro del dominio [1..100].
        """
        route = self._routes.get(route_id)
        if not route or not route.active:
            print(f"  ERROR: Ruta {route_id} no existe o no esta activa.")
            return False
        if new_order_id in route.order_ids:
            print(f"  AVISO: Pedido {new_order_id} ya esta en la ruta.")
            return False
        route.order_ids.append(new_order_id)

        def dest_number(oid: str) -> int:
            o = order_repo.get(oid)
            return o.destination.number if (o and o.destination) else 999

        route.order_ids.sort(key=dest_number)
        route.best_score = random.randint(ROUTE_DOMAIN_MIN, ROUTE_DOMAIN_MAX)
        route.tracking_log.append(
            f"Ajuste: pedido {new_order_id} agregado | orden={route.order_ids} | score={route.best_score}"
        )
        EventLogger().log(
            f"Ruta {route_id} ajustada -> orden={route.order_ids} | score={route.best_score}"
        )
        return True

    def track_route(self, route_id: str, event: str) -> bool:
        route = self._routes.get(route_id)
        if not route:
            return False
        route.tracking_log.append(event)
        EventLogger().log(f"Seguimiento {route_id}: {event}")
        return True

    def get_route(self, route_id: str) -> Optional[Route]:
        return self._routes.get(route_id)

    def all(self) -> list[Route]:
        return list(self._routes.values())

# ===========================================================================
# REPOSITORIO DE PEDIDOS
# SOLID S: solo CRUD en memoria
# ===========================================================================

class OrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def all(self) -> list[Order]:
        return list(self._orders.values())

# ===========================================================================
# TRACKING SERVICE
# SOLID S: solo visualizar, notificar y registrar eventos
# ===========================================================================

class TrackingService:
    def __init__(self, order_repo: OrderRepository,
                 courier_repo: CourierRepository,
                 notifier: INotifiable) -> None:
        self._order_repo   = order_repo
        self._courier_repo = courier_repo
        self._notifier     = notifier

    def visualize_status(self, order_id: str) -> None:
        order = self._order_repo.get(order_id)
        if not order:
            print(f"  AVISO: Pedido {order_id} no encontrado.")
            return
        courier_info = "sin asignar"
        if order.assigned_courier_id:
            c = self._courier_repo.get_by_id(order.assigned_courier_id)
            if c:
                courier_info = f"{c.name} (ID {c.courier_id}, ubicacion: {c.location})"
        print(f"  [{order.order_id}] {order.status.value} | Canal: {order.channel.value} | Repartidor: {courier_info}")

    def notify_client(self, order_id: str) -> None:
        order = self._order_repo.get(order_id)
        if not order:
            return
        self._notifier.notify(
            order.contact_medium,
            f"Tu pedido {order_id} esta en estado: {order.status.value}"
        )

    def record_event(self, order_id: str, event: str) -> None:
        order = self._order_repo.get(order_id)
        if order:
            order.add_event(event)
            EventLogger().log(f"Evento en {order_id}: {event}")

# ===========================================================================
# FACADE - LogisticsFacade
# SOLID D: depende de abstracciones inyectadas por constructor
# ===========================================================================

class LogisticsFacade:
    """[PATRON: FACADE] Punto de entrada unico al sistema."""
    def __init__(self, order_repo: OrderRepository,
                 courier_repo: CourierRepository,
                 route_manager: RouteManager,
                 validator: OrderValidator,
                 state_manager: OrderStateManager,
                 tracking: TrackingService,
                 factory: AbstractOrderFactory) -> None:
        self._order_repo    = order_repo
        self._courier_repo  = courier_repo
        self._route_manager = route_manager
        self._validator     = validator
        self._state_manager = state_manager
        self._tracking      = tracking
        self._factory       = factory
        self._logger        = EventLogger()

    # -- CU1: Gestion de Pedidos ---------------------------------------------

    def crear_pedido(self, order_id: str, raw_origin: dict, raw_destination: dict,
                     recipient_name: str, contact: str, delivery_type: DeliveryType,
                     cargo_type: str, weight_kg: float) -> Order:
        order = self._factory.get_channel().create_order(
            order_id, raw_origin, raw_destination,
            recipient_name, contact, delivery_type, cargo_type, weight_kg
        )
        self._order_repo.save(order)
        self._logger.log(f"Pedido creado: {order_id} | Canal: {order.channel.value}")
        return order

    def validar_pedido(self, order_id: str) -> bool:
        order = self._order_repo.get(order_id)
        if not order:
            print(f"  ERROR: Pedido {order_id} no existe.")
            return False
        ok, errors = self._validator.validate(order)
        if ok:
            self._state_manager.transition(order, OrderStatus.VALIDADO)
            self._state_manager.transition(order, OrderStatus.PENDIENTE_ASIGNACION)
            print(f"  OK: Pedido {order_id} validado.")
        else:
            print(f"  ERROR: Pedido {order_id} invalido:")
            for e in errors:
                print(f"    - {e}")
        return ok

    def cambiar_estado(self, order_id: str, new_status: OrderStatus) -> bool:
        order = self._order_repo.get(order_id)
        if not order:
            return False
        return self._state_manager.transition(order, new_status)

    # -- CU2: Monitoreo y Tracking -------------------------------------------

    def ver_estado(self, order_id: str) -> None:
        self._tracking.visualize_status(order_id)

    def notificar_cliente(self, order_id: str) -> None:
        self._tracking.notify_client(order_id)

    def registrar_evento(self, order_id: str, event: str) -> None:
        self._tracking.record_event(order_id, event)

    # -- CU3: Gestion de Repartidores ----------------------------------------

    def registrar_repartidor(self, name: str, max_volume_m3: float) -> Courier:
        return self._courier_repo.register(name, max_volume_m3)

    def gestionar_disponibilidad(self, courier_id: int, available: bool) -> None:
        self._courier_repo.set_availability(courier_id, available)

    def actualizar_ubicacion_repartidor(self, courier_id: int, location: int) -> bool:
        """CU3: El repartidor actualiza su ubicacion. Validado contra dominio [1..100]."""
        return self._courier_repo.update_location(courier_id, location)

    def asignar_pedido(self, order_id: str, order_volume: float = 0.0) -> bool:
        """CU3: Asigna al primer repartidor disponible con volumen suficiente."""
        order = self._order_repo.get(order_id)
        if not order or order.status != OrderStatus.PENDIENTE_ASIGNACION:
            print(f"  AVISO: Pedido {order_id} no esta en PENDIENTE_ASIGNACION.")
            return False
        available = self._courier_repo.get_available(order_volume)
        if not available:
            print(f"  AVISO: Sin repartidores con capacidad suficiente.")
            return False
        courier = available[0]
        courier.assign_order(order_id, order_volume)
        order.assigned_courier_id = courier.courier_id
        self._state_manager.transition(order, OrderStatus.ASIGNADO)
        self._logger.log(
            f"Pedido {order_id} asignado a {courier.name} (ID={courier.courier_id}) "
            f"| vol={courier.current_volume:.2f}/{courier.max_volume_m3}m3"
        )
        return True

    # -- CU4: Gestion de Rutas ------------------------------------------------

    def definir_ruta(self, order_ids: list[str]) -> Route:
        return self._route_manager.define_route(order_ids)

    def ajustar_ruta_dinamicamente(self, route_id: str, new_order_id: str) -> bool:
        """CU4: Agrega pedido a ruta activa y reordena por destino (optimizacion local)."""
        return self._route_manager.adjust_route(route_id, new_order_id, self._order_repo)

    def seguimiento_ruta(self, route_id: str, event: str) -> None:
        self._route_manager.track_route(route_id, event)

# ===========================================================================
# COMPOSICION DE DEPENDENCIAS (Dependency Injection manual)
# SOLID D: el grafo de dependencias se construye aqui
# ===========================================================================

def build_system(use_ecommerce: bool = False) -> LogisticsFacade:
    order_repo    = OrderRepository()
    courier_repo  = CourierRepository()
    route_manager = RouteManager()
    validator     = OrderValidator()
    state_manager = OrderStateManager()
    factory       = EcommerceFactory() if use_ecommerce else PropioFactory()
    notifier      = LoggingNotifierDecorator(factory.get_notifier())  # DECORATOR
    tracking      = TrackingService(order_repo, courier_repo, notifier)
    return LogisticsFacade(order_repo, courier_repo, route_manager,
                           validator, state_manager, tracking, factory)

# ===========================================================================
# HELPERS DE CONSOLA
# ===========================================================================

def _input_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        try:
            v = int(input(prompt))
            if lo <= v <= hi:
                return v
            print(f"  ERROR: Ingrese un numero entre {lo} y {hi}.")
        except ValueError:
            print("  ERROR: Numero invalido.")

def _input_float(prompt: str, lo: float = 0.01) -> float:
    while True:
        try:
            v = float(input(prompt))
            if v >= lo:
                return v
            print(f"  ERROR: El valor debe ser >= {lo}.")
        except ValueError:
            print("  ERROR: Numero invalido.")

def _menu(titulo: str, opciones: list[str]) -> int:
    print()
    print(SEP2)
    print(f"  {titulo}")
    print(SEP2)
    for i, op in enumerate(opciones, 1):
        print(f"  {i}. {op}")
    return _input_int("  -> Opcion: ", 1, len(opciones))

def _pedir_direccion(label: str) -> dict:
    print(f"\n  [ {label} ]")
    calle  = input("  Calle: ").strip() or "Sin nombre"
    nro    = _input_int(f"  Numero [{ROUTE_DOMAIN_MIN}-{ROUTE_DOMAIN_MAX}]: ",
                        ROUTE_DOMAIN_MIN, ROUTE_DOMAIN_MAX)
    ciudad = input("  Ciudad: ").strip() or "Local"
    return {"calle": calle, "nro": str(nro), "ciudad": ciudad}

# ===========================================================================
# FLUJOS INTERACTIVOS POR CASO DE USO
# ===========================================================================

def flujo_registrar_repartidor(sistema: LogisticsFacade) -> None:
    """CU3: Registrar repartidor con volumen maximo de carga."""
    print()
    print(SEP)
    print("  REGISTRAR REPARTIDOR")
    print(SEP)
    nombre = input("  Nombre: ").strip()
    if not nombre:
        print("  ERROR: Nombre obligatorio.")
        return
    vol = _input_float("  Volumen maximo de carga (m3, ej: 1.5): ", 0.01)
    c = sistema.registrar_repartidor(nombre, vol)
    print(f"  OK: Repartidor registrado | ID={c.courier_id} | vol_max={vol}m3")


def flujo_disponibilidad(sistema: LogisticsFacade) -> None:
    """CU3: Gestionar disponibilidad del repartidor."""
    couriers = sistema._courier_repo.all()
    if not couriers:
        print("  AVISO: No hay repartidores registrados.")
        return
    print()
    print(SEP)
    print("  GESTIONAR DISPONIBILIDAD")
    print(SEP)
    for c in couriers:
        est = "disponible" if c.available else "no disponible"
        print(f"  [{c.courier_id}] {c.name} - {est}")
    cid = _input_int("  ID del repartidor: ", 1, sistema._courier_repo._next_id - 1)
    op  = _menu("Cambiar a:", ["Disponible", "No disponible"])
    sistema.gestionar_disponibilidad(cid, op == 1)


def flujo_actualizar_ubicacion(sistema: LogisticsFacade) -> None:
    """CU3: El repartidor actualiza su ubicacion [1..100]."""
    couriers = sistema._courier_repo.all()
    if not couriers:
        print("  AVISO: No hay repartidores registrados.")
        return
    print()
    print(SEP)
    print("  ACTUALIZAR UBICACION REPARTIDOR")
    print(SEP)
    for c in couriers:
        print(f"  [{c.courier_id}] {c.name} - ubicacion actual: {c.location}")
    cid = _input_int("  ID del repartidor: ", 1, sistema._courier_repo._next_id - 1)
    loc = _input_int(f"  Nueva ubicacion [{ROUTE_DOMAIN_MIN}-{ROUTE_DOMAIN_MAX}]: ",
                     ROUTE_DOMAIN_MIN, ROUTE_DOMAIN_MAX)
    ok = sistema.actualizar_ubicacion_repartidor(cid, loc)
    if ok:
        print(f"  OK: Ubicacion actualizada a {loc}.")


def flujo_crear_pedido(sistema: LogisticsFacade, contador: list) -> None:
    """CU1: Crear, validar y asignar pedido."""
    print()
    print(SEP)
    print("  CREAR PEDIDO")
    print(SEP)
    contador[0] += 1
    order_id = f"PED-{contador[0]:03d}"
    print(f"  ID generado: {order_id}")

    raw_origin = _pedir_direccion("DIRECCION DE ORIGEN")
    raw_dest   = _pedir_direccion("DIRECCION DE DESTINO")

    print()
    recipient = input("  Nombre destinatario: ").strip()
    if not recipient:
        print("  ERROR: Nombre obligatorio.")
        return
    contact = input("  Contacto (email/telefono): ").strip()
    if not contact:
        print("  ERROR: Contacto obligatorio.")
        return

    op = _menu("Tipo de entrega:", [e.value for e in DeliveryType])
    delivery = list(DeliveryType)[op - 1]

    cargo  = input("  Tipo de carga (ej: electronico, ropa): ").strip() or "general"
    weight = _input_float("  Peso (kg): ", 0.01)
    vol    = _input_float("  Volumen del pedido (m3, ej: 0.2): ", 0.001)

    sistema.crear_pedido(order_id, raw_origin, raw_dest,
                         recipient, contact, delivery, cargo, weight)
    if sistema.validar_pedido(order_id):
        sistema.asignar_pedido(order_id, order_volume=vol)
        sistema.notificar_cliente(order_id)


def flujo_ver_pedidos(sistema: LogisticsFacade) -> None:
    """CU2: Visualizar estado de todos los pedidos."""
    print()
    print(SEP)
    print("  ESTADO DE PEDIDOS")
    print(SEP)
    pedidos = sistema._order_repo.all()
    if not pedidos:
        print("  Sin pedidos registrados.")
        return
    for o in pedidos:
        sistema.ver_estado(o.order_id)


def flujo_gestionar_estado(sistema: LogisticsFacade) -> None:
    """CU1: Cambiar estado de un pedido y notificar al cliente."""
    pedidos = sistema._order_repo.all()
    if not pedidos:
        print("  AVISO: No hay pedidos.")
        return
    print()
    print(SEP)
    print("  GESTIONAR ESTADO DE PEDIDO")
    print(SEP)

    # Seleccionar pedido desde lista numerada (evita error de tipeo en ID)
    lista = list(pedidos)
    for i, o in enumerate(lista, 1):
        print(f"  {i}. [{o.order_id}] Estado actual: {o.status.value}")
    idx = _input_int("  Seleccione pedido: ", 1, len(lista)) - 1
    order = lista[idx]

    # Mostrar solo las transiciones validas desde el estado actual
    transiciones_validas = OrderStateManager._TRANSITIONS.get(order.status, [])
    if not transiciones_validas:
        print(f"  AVISO: El pedido ya esta en estado final ({order.status.value}). No admite cambios.")
        return

    print(f"\n  Estados posibles desde '{order.status.value}':")
    op = _menu("Nuevo estado:", [s.value for s in transiciones_validas])
    nuevo = transiciones_validas[op - 1]

    ok = sistema.cambiar_estado(order.order_id, nuevo)
    if ok:
        print(f"  OK: Estado cambiado a {nuevo.value}.")
        sistema.notificar_cliente(order.order_id)
    else:
        print(f"  ERROR: No se pudo cambiar el estado.")


def flujo_rutas(sistema: LogisticsFacade) -> None:
    """CU4: Gestion de rutas."""
    op = _menu("GESTION DE RUTAS:", [
        "Definir nueva ruta",
        "Ajuste dinamico (agregar pedido a ruta existente)",
        "Registrar evento de seguimiento",
        "Ver todas las rutas",
    ])

    if op == 1:
        pedidos = sistema._order_repo.all()
        if not pedidos:
            print("  AVISO: No hay pedidos disponibles.")
            return
        print("  Pedidos:")
        for o in pedidos:
            print(f"    [{o.order_id}] {o.status.value}")
        ids_str = input("  IDs separados por coma (ej: PED-001,PED-002): ")
        ids = [x.strip() for x in ids_str.split(",") if x.strip()]
        if ids:
            ruta = sistema.definir_ruta(ids)
            print(f"  OK: Ruta {ruta.route_id} creada | score={ruta.best_score}")

    elif op == 2:
        rutas = sistema._route_manager.all()
        if not rutas:
            print("  AVISO: No hay rutas definidas.")
            return
        print("  Rutas activas:")
        for r in rutas:
            print(f"    [{r.route_id}] pedidos={r.order_ids} | score={r.best_score}")
        rid = input("  ID de la ruta: ").strip()
        oid = input("  ID del pedido a agregar: ").strip()
        ok  = sistema.ajustar_ruta_dinamicamente(rid, oid)
        if ok:
            ruta = sistema._route_manager.get_route(rid)
            print(f"  OK: Ruta ajustada | orden={ruta.order_ids} | score={ruta.best_score}")

    elif op == 3:
        rid   = input("  ID de la ruta: ").strip()
        event = input("  Evento de seguimiento: ").strip()
        sistema.seguimiento_ruta(rid, event)
        print("  OK: Evento registrado.")

    elif op == 4:
        rutas = sistema._route_manager.all()
        if not rutas:
            print("  Sin rutas registradas.")
            return
        for r in rutas:
            print(f"\n  RUTA {r.route_id} | activa={r.active} | score={r.best_score}")
            print(f"  pedidos: {r.order_ids}")
            for entry in r.tracking_log:
                print(f"    - {entry}")


def flujo_ver_repartidores(sistema: LogisticsFacade) -> None:
    """CU3: Ver estado de todos los repartidores."""
    print()
    print(SEP)
    print("  REPARTIDORES")
    print(SEP)
    couriers = sistema._courier_repo.all()
    if not couriers:
        print("  Sin repartidores registrados.")
        return
    for c in couriers:
        est = "disponible" if c.available else "no disponible"
        print(f"  [{c.courier_id}] {c.name} | {est} | ubicacion: {c.location} | "
              f"vol {c.current_volume:.2f}/{c.max_volume_m3}m3 | "
              f"pedidos: {c.current_orders if c.current_orders else 'ninguno'}")


def flujo_historial(sistema: LogisticsFacade) -> None:
    """CU2: Historial completo de eventos (EventLogger Singleton)."""
    print()
    print(SEP)
    print("  HISTORIAL DE EVENTOS")
    print(SEP)
    eventos = EventLogger().get_events()
    if not eventos:
        print("  Sin eventos registrados.")
        return
    for i, ev in enumerate(eventos, 1):
        print(f"  [{i:3d}] {ev}")


# ===========================================================================
# MENU PRINCIPAL
# ===========================================================================

def main() -> None:
    print()
    print(SEP)
    print("  SISTEMA DE LOGISTICA DE ULTIMA MILLA")
    print(SEP)

    op = _menu("Seleccione el canal del sistema:", ["Canal Propio", "E-Commerce"])
    sistema = build_system(use_ecommerce=(op == 2))
    canal   = "E-Commerce" if op == 2 else "Canal Propio"
    print(f"\n  Sistema iniciado - Canal: {canal}")

    contador = [0]

    OPCIONES = [
        "CU3 - Registrar repartidor",
        "CU3 - Gestionar disponibilidad",
        "CU3 - Actualizar ubicacion de repartidor",
        "CU1 - Crear pedido",
        "CU1 - Cambiar estado de pedido",
        "CU2 - Ver estado de pedidos",
        "CU3 - Ver repartidores",
        "CU4 - Gestion de rutas",
        "CU2 - Ver historial de eventos",
        "Salir",
    ]

    while True:
        sel = _menu("MENU PRINCIPAL", OPCIONES)
        if   sel == 1:  flujo_registrar_repartidor(sistema)
        elif sel == 2:  flujo_disponibilidad(sistema)
        elif sel == 3:  flujo_actualizar_ubicacion(sistema)
        elif sel == 4:  flujo_crear_pedido(sistema, contador)
        elif sel == 5:  flujo_gestionar_estado(sistema)
        elif sel == 6:  flujo_ver_pedidos(sistema)
        elif sel == 7:  flujo_ver_repartidores(sistema)
        elif sel == 8:  flujo_rutas(sistema)
        elif sel == 9:  flujo_historial(sistema)
        elif sel == 10:
            print()
            print(SEP)
            print("  Hasta luego!")
            print(SEP)
            break


if __name__ == "__main__":
    main()