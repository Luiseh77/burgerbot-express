from ai_service import obtener_respuesta_ia

historial = []

print("=====================================================")
print("🤖 SIMULADOR LOCAL DEL BOT DE BURGERBOT EXPRESS 🤖")
print("=====================================================")
print("(Escribe 'salir' en cualquier momento para terminar)\n")

while True:
    usuario = input("Tú (Cliente): ")
    if usuario.lower() == "salir":
        break
        
    # Guardamos lo que dijo el usuario en la memoria de la conversación
    historial.append({"role": "user", "content": usuario})
    
    # Procesamos con la Inteligencia Artificial (Llama 3 en Groq)
    try:
        respuesta = obtener_respuesta_ia(historial)
        
        if respuesta["tipo"] == "texto":
            bot_texto = respuesta["contenido"]
            print(f"\n🍔 Asistente: {bot_texto}\n")
            
            # Guardamos la respuesta del bot en la memoria
            historial.append({"role": "assistant", "content": bot_texto})
            
        elif respuesta["tipo"] == "pedido_completado":
            datos_pedido = respuesta["contenido"]
            print("\n✅ ¡BINGO! EL BOT EXTRAJO LOS DATOS INICIALES (NOMBRE, ZONA, MÉTODO DE PAGO).")
            print(f"Datos: {datos_pedido}")
            
            # Guardamos el pedido real en Supabase
            from db_service import guardar_pedido_nuevo, supabase
            print("\n💾 Guardando pedido en la nube con estado ESPERANDO_PAGO...")
            resultado_db = guardar_pedido_nuevo(datos_pedido)
            
            if resultado_db:
                pedido_id = resultado_db['id']
                print(f"✅ Pedido #{pedido_id} guardado con éxito.")
                
                # Simulación de la Captura de Pantalla del Pago
                print("\n📱 El bot se queda en silencio esperando que el cliente mande la captura del pago...")
                input("\n>> Presiona ENTER para simular que el cliente envía la Captura de Pantalla... ")
                
                print("\n📸 [CAPTURA RECIBIDA] Actualizando estado a PAGO_POR_VALIDAR...")
                if supabase:
                    supabase.table("pedidos").update({"estado": "PAGO_POR_VALIDAR"}).eq("id", pedido_id).execute()
                
                # Simulación de la Aprobación del Administrador
                print("\n🧑‍💻 [HUMANO/ADMIN]: Te llega una notificación en WhatsApp con botones para aprobar/rechazar.")
                input(">> Presiona ENTER para simular que apruebas el pago (Aprobar)... ")
                
                print("\n✅ Pago aprobado por el Administrador. Cambiando estado a ESPERANDO_DIRECCION.")
                if supabase:
                    supabase.table("pedidos").update({"estado": "ESPERANDO_DIRECCION"}).eq("id", pedido_id).execute()
                
                # Simulación: Cliente escribe la dirección exacta
                print(f"\n💬 El bot le envía un mensaje al cliente solicitando su dirección escrita.")
                dir_escrita = input("\nTú (Cliente - Escribe tu dirección exacta): ")
                
                if supabase:
                    # Traemos dirección previa ("Zona: Tigre") y le concatenamos la escrita
                    res_ped = supabase.table("pedidos").select("direccion").eq("id", pedido_id).execute()
                    dir_prev = res_ped.data[0]["direccion"] if res_ped.data else "Zona: N/A"
                    dir_completa = f"{dir_prev} | Dirección: {dir_escrita}"
                    
                    supabase.table("pedidos").update({
                        "direccion": dir_completa,
                        "estado": "ESPERANDO_UBICACION"
                    }).eq("id", pedido_id).execute()
                    
                # Simulación: Cliente envía ubicación de Google Maps
                print(f"\n💬 El bot le envía un mensaje al cliente solicitando su ubicación GPS (Google Maps).")
                maps_link = input("\nTú (Cliente - Pega enlace de Google Maps o escribe 'ubicacion_gps'): ")
                if maps_link == "ubicacion_gps":
                    maps_link = "https://maps.google.com/?q=8.9,-64.2"
                
                if supabase:
                    supabase.table("pedidos").update({
                        "ubicacion_maps": maps_link,
                        "estado": "PENDIENTE"
                    }).eq("id", pedido_id).execute()
                
                print("\n📡 ¡DATOS DE ENTREGA COMPLETADOS!")
                print(f"👉 Dirección en BD: {dir_completa if 'dir_completa' in locals() else 'N/A'}")
                print(f"👉 Ubicación GPS en BD: {maps_link}")
                print("\n🛵 SIMULANDO BROADCAST A REPARTIDORES:")
                print(f"👉 '¡NUEVO PEDIDO LISTO PARA ENTREGAR! Zona: {datos_pedido.get('zona_delivery', 'N/A')}. Cobro Total: ${datos_pedido.get('gran_total', '0.0')} [Botón: ¡Yo lo llevo!]'")
            else:
                print("❌ Hubo un error al guardar en la base de datos. Revisa tus llaves en el .env")
            
            break
            
    except Exception as e:
        print(f"\n❌ Error al comunicarse con Gemini. Revisa tu .env")
        print(f"Detalle: {e}\n")
        break
