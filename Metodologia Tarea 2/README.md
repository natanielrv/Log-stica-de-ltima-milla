## Requisitos
pip install flask

## Ejecutar
python app.py
→ http://localhost:5000 
→ abrir postman y hacer los post/get/put necesarios

## Roles y prefijos de los URL
| Prefijo         | Quién lo usa                  | Qué puede hacer                                      |
|-----------------|-------------------------------|------------------------------------------------------|
| /cliente/...    | Cliente final                 | Crear pedido, ver tracking propio                    |
| /repartidor/... | Repartidor                    | Registrarse, disponibilidad, ubicacion, estado pedido|
| /sistema/...    | Operador logístico            | Asignar pedidos, definir/ajustar rutas               |
| /admin/...      | Administrador                 | Ver pedidos, repartidores, historial (solo lectura)  |

## Roles y prefijos de URL
| Prefijo         | Quién lo usa                  | Qué puede hacer                                                        
|-----------------|-------------------------------|------------------------------------------------------------------------     
| /cliente/...    | Cliente final                 | Crear pedido por canal, ver tracking propio                                 
| /repartidor/... | Repartidor                    | Registrarse, disponibilidad, actualizar ubicación, cambiar estado de pedido 
| /sistema/...    | Sistema logistico             | Asignar pedidos, definir rutas, ajustar rutas, registrar seguimiento        
| /admin/...      | Administrador                 | Ver pedidos, repartidores, historial de eventos (solo lectura)         