"""

 REVISAR ESTO
   PATRONES ARQUITECTÓNICOS APLICADOS:
  - Service Layer : LogisticsFacade actúa como capa de servicio 
  - Repository    : OrderRepository y CourierRepository 
  - MVC           : Controllers (funciones Flask) → Service (Facade) → Model (entidades)
  - Data Mapper   : _order_to_dict / _courier_to_dict / _route_to_dict 

ROLES Y PREFIJOS DE URL:
  /cliente/...       cliente: crea pedidos y ve su tracking
  /repartidor/...    repartidor: se registra, gestiona disponibilidad, actualiza ubicación y estado
  /sistema/...       administrador: ve historial y lista de repartidores/pedidos

CARGA VARIABLE: threaded=True permite múltiples requests concurrentes
DISPONIBILIDAD:  errorhandler global evita caídas del servicio
"""

from flask import Flask, request, jsonify
from logistica_ultima_milla import (
    build_system, DeliveryType, OrderStatus, EventLogger
)

app = Flask(__name__)

# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================
sistema = build_system(use_ecommerce=False)
_order_counter = [0]


# =============================================================================
# DATA MAPPER: convierte los objetos del sistema en datos con formato JSON.
# =============================================================================

def _order_to_dict(order) -> dict:
    return {
        "order_id":      order.order_id,
        "channel":       order.channel.value,
        "status":        order.status.value,
        "origin": {
            "calle":  order.origin.street,
            "nro":    order.origin.number,
            "ciudad": order.origin.city,
        } if order.origin else None,
        "destination": {
            "calle":  order.destination.street,
            "nro":    order.destination.number,
            "ciudad": order.destination.city,
        } if order.destination else None,
        "destinatario":  order.recipient_name,
        "contacto":      order.contact_medium,
        "tipo_entrega":  order.delivery_type.value if order.delivery_type else None,
        "tipo_carga":    order.cargo_type,
        "peso_kg":       order.weight_kg,
        "repartidor_id": order.assigned_courier_id,
        "ruta_id":       order.route_id,
        "eventos":       order.events,
    }

def _courier_to_dict(c) -> dict:
    return {
        "courier_id":     c.courier_id,
        "nombre":         c.name,
        "volumen_max":    c.max_volume_m3,
        "disponible":     c.available,
        "volumen_actual": c.current_volume,
        "pedidos":        c.current_orders,
        "ubicacion":      c.location,
    }

def _route_to_dict(r) -> dict:
    return {
        "route_id":    r.route_id,
        "pedidos":     r.order_ids,
        "score":       r.best_score,
        "activa":      r.active,
        "seguimiento": r.tracking_log,
    }


# =============================================================================
# DISPONIBILIDAD CONTINUA: manejo global de excepciones
# =============================================================================

@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({
        "success": False,
        "error":   f"Error interno del servidor: {str(e)}",
        "hint":    "El servicio sigue operativo."
    }), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "Endpoint no encontrado."}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"success": False, "error": "Metodo HTTP no permitido."}), 405


# =============================================================================
# Verificar que el sistema funciona correctamente
# =============================================================================

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "service": "Logistica de Ultima Milla - Web Service",
        "version": "2.0",
        "status":  "running",
        "roles": {
            "cliente":    "Crear pedidos y ver su propio tracking",
            "repartidor": "Registrarse, gestionar disponibilidad, actualizar ubicacion y estado de pedidos",
            "sistema":    "Asignar pedidos y gestionar rutas",
            "admin":      "Ver historial de eventos y listar repartidores/pedidos",
            "venta":      "Crear pedidos via canal e-commerce",
        },
        "endpoints": {
            "cliente":    ["POST /cliente/pedidos",
                           "GET  /cliente/tracking/<id>"],
            "repartidor": ["POST /repartidor/registrar",
                           "PUT  /repartidor/disponibilidad/<id>",
                           "PUT  /repartidor/ubicacion/<id>",
                           "PUT  /repartidor/pedidos/<id>/estado",
                           "GET  /repartidor/pedidos?courier_id=<id>"],
            "sistema":    ["POST /sistema/pedidos/<id>/asignar",
                           "POST /sistema/rutas",
                           "GET  /sistema/rutas",
                           "POST /sistema/rutas/<id>/ajustar",
                           "POST /sistema/rutas/<id>/seguimiento"],
            "admin":      ["GET  /admin/repartidores",
                           "GET  /admin/pedidos",
                           "GET  /admin/eventos"],
        }
    }), 200


# =============================================================================
# CLIENTE
# Crear pedido 
# Ver su propio tracking
# =============================================================================

@app.route("/cliente/pedidos", methods=["POST"])
def cliente_crear_pedido():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Body JSON requerido."}), 400

    canal_str = data.get("canal", "CANAL_PROPIO").upper()
    if canal_str == "ECOMMERCE":
        from logistica_ultima_milla import EcommerceFactory
        factory = EcommerceFactory()
    else:
        from logistica_ultima_milla import PropioFactory
        factory = PropioFactory()

    tipo_str = data.get("tipo_entrega", "NORMAL").upper()
    try:
        delivery_type = DeliveryType(tipo_str)
    except ValueError:
        return jsonify({
            "success": False,
            "error":   f"tipo_entrega invalido. Validos: {[e.value for e in DeliveryType]}"
        }), 422

    _order_counter[0] += 1
    order_id = f"PED-{_order_counter[0]:03d}"

    order = factory.get_channel().create_order(
        order_id,
        data.get("origen", {}),
        data.get("destino", {}),
        data.get("destinatario", ""),
        data.get("contacto", ""),
        delivery_type,
        data.get("tipo_carga", ""),
        float(data.get("peso_kg", 0)),
    )
    sistema._order_repo.save(order)

    ok, errors = sistema._validator.validate(order)
    if not ok:
        return jsonify({"success": False, "order_id": order_id, "errores": errors}), 422

    sistema._state_manager.transition(order, OrderStatus.VALIDADO)
    sistema._state_manager.transition(order, OrderStatus.PENDIENTE_ASIGNACION)

    vol      = float(data.get("volumen_m3", 0.0))
    asignado = sistema.asignar_pedido(order_id, order_volume=vol)
    sistema.notificar_cliente(order_id)

    return jsonify({
        "success":  True,
        "canal":    canal_str,
        "asignado": asignado,
        "order":    _order_to_dict(order),
    }), 201


@app.route("/cliente/tracking/<order_id>", methods=["GET"])
def cliente_tracking(order_id):
    """CU2 – Cliente consulta el estado de su propio pedido."""
    order = sistema._order_repo.get(order_id)
    if not order:
        return jsonify({"success": False, "error": f"Pedido {order_id} no encontrado."}), 404

    resultado = _order_to_dict(order)
    if order.assigned_courier_id:
        c = sistema._courier_repo.get_by_id(order.assigned_courier_id)
        if c:
            resultado["repartidor_info"] = {
                "nombre":    c.name,
                "ubicacion": c.location,
            }
    return jsonify({"success": True, "tracking": resultado}), 200


# =============================================================================
# REPARTIDOR
# Registrarse, gestionar disponibilidad, actualizar ubicación
# Cambiar estado del pedido (EN_RUTA, ENTREGADO, INTENTO_FALLIDO)
# Ve sus pedidos asignados
# =============================================================================

@app.route("/repartidor/registrar", methods=["POST"])
def repartidor_registrar():
    """
    CU3 – Repartidor se registra en el sistema.
    Body: {"nombre": "Carlos Lopez", "volumen_max": 2.0}
    """
    data        = request.get_json(silent=True) or {}
    nombre      = data.get("nombre", "").strip()
    volumen_max = float(data.get("volumen_max", 0))

    if not nombre:
        return jsonify({"success": False, "error": "Campo 'nombre' requerido."}), 422
    if volumen_max <= 0:
        return jsonify({"success": False, "error": "volumen_max debe ser > 0."}), 422

    courier = sistema.registrar_repartidor(nombre, volumen_max)
    return jsonify({"success": True, "repartidor": _courier_to_dict(courier)}), 201


@app.route("/repartidor/disponibilidad/<int:courier_id>", methods=["PUT"])
def repartidor_disponibilidad(courier_id):
    """
    CU3 – Repartidor actualiza su propia disponibilidad.
    Body: {"disponible": true}
    """
    data = request.get_json(silent=True) or {}
    c    = sistema._courier_repo.get_by_id(courier_id)
    if not c:
        return jsonify({"success": False, "error": f"Repartidor {courier_id} no existe."}), 404

    disponible = bool(data.get("disponible", True))
    sistema.gestionar_disponibilidad(courier_id, disponible)
    return jsonify({"success": True, "repartidor": _courier_to_dict(c)}), 200


@app.route("/repartidor/ubicacion/<int:courier_id>", methods=["PUT"])
def repartidor_ubicacion(courier_id):
    """
    CU3 – Repartidor actualiza su ubicación en tiempo real.
    Estado no crítico: consistencia eventual aceptable.
    Body: {"ubicacion": 42}
    """
    data = request.get_json(silent=True) or {}
    loc  = int(data.get("ubicacion", -1))

    c = sistema._courier_repo.get_by_id(courier_id)
    if not c:
        return jsonify({"success": False, "error": f"Repartidor {courier_id} no existe."}), 404

    ok = sistema.actualizar_ubicacion_repartidor(courier_id, loc)
    if not ok:
        return jsonify({"success": False,
                        "error": f"Ubicacion {loc} fuera del dominio [1-100]."}), 400

    return jsonify({
        "success":    True,
        "nota":       "Consistencia eventual: estado no critico.",
        "repartidor": _courier_to_dict(c),
    }), 200


@app.route("/repartidor/pedidos/<order_id>/estado", methods=["PUT"])
def repartidor_cambiar_estado(order_id):
    """
    CU1 – Repartidor cambia el estado de un pedido en terreno.
    Solo puede cambiar a: EN_RUTA, ENTREGADO, INTENTO_FALLIDO.
    Body: {"status": "EN_RUTA"}
    """
    ESTADOS_REPARTIDOR = ["EN_RUTA", "ENTREGADO", "INTENTO_FALLIDO"]
    data       = request.get_json(silent=True) or {}
    status_str = data.get("status", "").upper()

    if status_str not in ESTADOS_REPARTIDOR:
        return jsonify({
            "success": False,
            "error":   f"El repartidor solo puede cambiar a: {ESTADOS_REPARTIDOR}"
        }), 403

    try:
        new_status = OrderStatus(status_str)
    except ValueError:
        return jsonify({"success": False, "error": "Estado invalido."}), 422

    order = sistema._order_repo.get(order_id)
    if not order:
        return jsonify({"success": False,
                        "error": f"Pedido {order_id} no encontrado."}), 404

    ok = sistema.cambiar_estado(order_id, new_status)
    if not ok:
        permitidos = [s.value for s in sistema._state_manager._TRANSITIONS.get(order.status, [])]
        return jsonify({
            "success":            False,
            "error":              f"Transicion invalida desde '{order.status.value}'.",
            "estados_permitidos": permitidos,
        }), 400

    sistema.notificar_cliente(order_id)
    return jsonify({"success": True, "order": _order_to_dict(order)}), 200


@app.route("/repartidor/pedidos", methods=["GET"])
def repartidor_ver_pedidos():
    """
    CU2 – Repartidor ve sus pedidos asignados.
    Query param: ?courier_id=1
    """
    courier_id = request.args.get("courier_id", type=int)
    if not courier_id:
        return jsonify({"success": False,
                        "error": "Query param requerido. Ej: /repartidor/pedidos?courier_id=1"}), 400

    c = sistema._courier_repo.get_by_id(courier_id)
    if not c:
        return jsonify({"success": False,
                        "error": f"Repartidor {courier_id} no existe."}), 404

    pedidos = [_order_to_dict(sistema._order_repo.get(oid))
               for oid in c.current_orders
               if sistema._order_repo.get(oid)]

    return jsonify({
        "success":    True,
        "repartidor": c.name,
        "ubicacion":  c.location,
        "pedidos":    pedidos,
    }), 200


# =============================================================================
# SISTEMA 
# Asigna pedidos
# Gestiona rutas
# =============================================================================

@app.route("/sistema/pedidos/<order_id>/asignar", methods=["POST"])
@app.route("/sistema/pedidos/<order_id>/asignar", methods=["POST"])
def sistema_asignar_pedido(order_id):
    """
    CU3 – Sistema asigna pedido. 
    Soporta asignación manual por 'courier_id' o automática por 'volumen_m3'.
    """
    data = request.get_json(silent=True) or {}
    courier_id = data.get("courier_id")
    vol = float(data.get("volumen_m3", 0.5))

    order = sistema._order_repo.get(order_id)
    if not order:
        return jsonify({"success": False, "error": f"Pedido {order_id} no encontrado."}), 404

    # Validación de estado: solo se puede asignar si está pendiente
    if order.status != OrderStatus.PENDIENTE_ASIGNACION:
        return jsonify({
            "success": False, 
            "error": f"El pedido debe estar en PENDIENTE_ASIGNACION (Actual: {order.status.value})"
        }), 400

    # Lógica de asignación manual por ID (Lo que envías en Postman)
    if courier_id:
        courier = sistema._courier_repo.get_by_id(int(courier_id))
        if not courier:
            return jsonify({"success": False, "error": f"Repartidor {courier_id} no existe."}), 404
        
        # Validar capacidad antes de asignar
        if not courier.can_accept(vol):
             return jsonify({"success": False, "error": "Repartidor sin capacidad suficiente."}), 409
             
        courier.assign_order(order_id, vol)
        order.assigned_courier_id = courier.courier_id
        sistema._state_manager.transition(order, OrderStatus.ASIGNADO)
        
        return jsonify({
            "success": True, 
            "order": _order_to_dict(order), 
            "repartidor": _courier_to_dict(courier)
        }), 200

    # Lógica de asignación automática (Si no envías courier_id)
    disponibles = sistema._courier_repo.get_available(vol)
    if not disponibles:
        return jsonify({"success": False, "error": "Sin repartidores disponibles."}), 409

    ok = sistema.asignar_pedido(order_id, order_volume=vol)
    if not ok:
        return jsonify({"success": False, "error": "No se pudo realizar la asignación."}), 400

    courier = sistema._courier_repo.get_by_id(order.assigned_courier_id)
    return jsonify({
        "success": True,
        "order": _order_to_dict(order),
        "repartidor": _courier_to_dict(courier)
    }), 200
def sistema_definir_ruta():
    """
    CU4 – Sistema define una nueva ruta optimizada.
    Body: {"order_ids": ["PED-001", "PED-002"]}
    """
    data      = request.get_json(silent=True) or {}
    order_ids = data.get("order_ids", [])

    if not order_ids:
        return jsonify({"success": False,
                        "error": "Se requiere al menos un pedido en 'order_ids'."}), 422

    no_existen = [oid for oid in order_ids if not sistema._order_repo.get(oid)]
    if no_existen:
        return jsonify({"success": False,
                        "error": f"Pedidos no encontrados: {no_existen}"}), 404

    ruta = sistema.definir_ruta(order_ids)
    return jsonify({"success": True, "ruta": _route_to_dict(ruta)}), 201


@app.route("/sistema/rutas", methods=["GET"])
def sistema_listar_rutas():
    """CU4 – Sistema lista todas las rutas activas."""
    rutas = sistema._route_manager.all()
    return jsonify({
        "success": True,
        "total":   len(rutas),
        "rutas":   [_route_to_dict(r) for r in rutas],
    }), 200


@app.route("/sistema/rutas/<route_id>/ajustar", methods=["POST"])
def sistema_ajustar_ruta(route_id):
    """
    CU4 – Sistema agrega un pedido a ruta activa y reordena.
    Body: {"order_id": "PED-002"}
    """
    data     = request.get_json(silent=True) or {}
    order_id = data.get("order_id", "").strip()

    if not order_id:
        return jsonify({"success": False, "error": "Campo 'order_id' requerido."}), 400

    ruta = sistema._route_manager.get_route(route_id)
    if not ruta:
        return jsonify({"success": False,
                        "error": f"Ruta {route_id} no encontrada."}), 404
    if not ruta.active:
        return jsonify({"success": False,
                        "error": f"Ruta {route_id} no esta activa."}), 400
    if order_id in ruta.order_ids:
        return jsonify({"success": False,
                        "error": f"Pedido {order_id} ya esta en la ruta."}), 409
    if not sistema._order_repo.get(order_id):
        return jsonify({"success": False,
                        "error": f"Pedido {order_id} no existe."}), 404

    ok = sistema.ajustar_ruta_dinamicamente(route_id, order_id)
    if not ok:
        return jsonify({"success": False, "error": "No se pudo ajustar la ruta."}), 400

    return jsonify({"success": True, "ruta": _route_to_dict(ruta)}), 200


@app.route("/sistema/rutas/<route_id>/seguimiento", methods=["POST"])
def sistema_seguimiento_ruta(route_id):
    """
    CU4 – Sistema registra evento de seguimiento en ruta.
    Body: {"evento": "Repartidor en zona norte"}
    """
    data   = request.get_json(silent=True) or {}
    evento = data.get("evento", "").strip()
    if not evento:
        return jsonify({"success": False, "error": "Campo 'evento' requerido."}), 400

    ruta = sistema._route_manager.get_route(route_id)
    if not ruta:
        return jsonify({"success": False,
                        "error": f"Ruta {route_id} no encontrada."}), 404

    sistema.seguimiento_ruta(route_id, evento)
    return jsonify({"success": True, "ruta": _route_to_dict(ruta)}), 201


# =============================================================================
# ADMIN
# Solo vista: pedidos, repartidores, historial de eventos
# =============================================================================

@app.route("/admin/repartidores", methods=["GET"])
def admin_listar_repartidores():
    """CU3 – Admin ve todos los repartidores registrados y su estado."""
    couriers = sistema._courier_repo.all()
    return jsonify({
        "success":      True,
        "total":        len(couriers),
        "repartidores": [_courier_to_dict(c) for c in couriers],
    }), 200


@app.route("/admin/pedidos", methods=["GET"])
def admin_listar_pedidos():
    """CU1/CU2 – Admin ve todos los pedidos del sistema."""
    pedidos = sistema._order_repo.all()
    return jsonify({
        "success": True,
        "total":   len(pedidos),
        "pedidos": [_order_to_dict(o) for o in pedidos],
    }), 200


@app.route("/admin/eventos", methods=["GET"])
def admin_historial():
    """CU2 – Admin ve el historial completo de eventos del sistema."""
    return jsonify({
        "success": True,
        "eventos": EventLogger().get_events(),
    }), 200


# =============================================================================
# CARGA VARIABLE – threaded=True permite múltiples requests simultaneos
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Logistica de Ultima Milla - Web Service v2.0")
    print("  http://localhost:5000")
    print("  /cliente  /repartidor  /sistema  /admin ")
    print("="*60 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
