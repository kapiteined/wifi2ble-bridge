#include "mesh_emu/bridge.h"
#include "mesh_emu/log.h"

#ifndef inline
#define inline __inline__
#endif

#include <arpa/inet.h>
#include <bluetooth/bluetooth.h>
#include <bluetooth/rfcomm.h>
#include <errno.h>
#include <netinet/in.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#define MESH_EMU_TCP_BUFFER_SIZE 1024

static int mesh_emu_bridge_send_all(int socket_fd, const char *buffer, int length)
{
    int total_sent;

    total_sent = 0;
    while (total_sent < length) {
        int sent_bytes;

        sent_bytes = (int)send(socket_fd, buffer + total_sent, (size_t)(length - total_sent), 0);
        if (sent_bytes < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (sent_bytes == 0) {
            return -1;
        }

        total_sent += sent_bytes;
    }

    return 0;
}

static int mesh_emu_bridge_connect_to_bluetooth(const char *address, int channel)
{
    int socket_fd;
    struct sockaddr_rc target_address;

    if (address == 0) {
        return -1;
    }

    socket_fd = socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM);
    if (socket_fd < 0) {
        return -1;
    }

    memset(&target_address, 0, sizeof(target_address));
    target_address.rc_family = AF_BLUETOOTH;
    target_address.rc_channel = (unsigned char)channel;
    str2ba(address, &target_address.rc_bdaddr);

    if (connect(socket_fd, (struct sockaddr *)&target_address, sizeof(target_address)) != 0) {
        close(socket_fd);
        return -1;
    }

    return socket_fd;
}

static int mesh_emu_bridge_proxy_between_sockets(int first_socket, int second_socket)
{
    char buffer[MESH_EMU_TCP_BUFFER_SIZE];

    for (;;) {
        fd_set read_fds;
        int highest_fd;
        int select_result;

        FD_ZERO(&read_fds);
        FD_SET(first_socket, &read_fds);
        FD_SET(second_socket, &read_fds);

        highest_fd = first_socket > second_socket ? first_socket : second_socket;
        select_result = select(highest_fd + 1, &read_fds, 0, 0, 0);
        if (select_result < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }

        if (FD_ISSET(first_socket, &read_fds)) {
            int received_bytes;

            received_bytes = (int)recv(first_socket, buffer, sizeof(buffer), 0);
            if (received_bytes <= 0) {
                return 0;
            }

            if (mesh_emu_bridge_send_all(second_socket, buffer, received_bytes) != 0) {
                return -1;
            }
        }

        if (FD_ISSET(second_socket, &read_fds)) {
            int received_bytes;

            received_bytes = (int)recv(second_socket, buffer, sizeof(buffer), 0);
            if (received_bytes <= 0) {
                return 0;
            }

            if (mesh_emu_bridge_send_all(first_socket, buffer, received_bytes) != 0) {
                return -1;
            }
        }
    }
}

void mesh_emu_bridge_init(struct mesh_emu_bridge *bridge)
{
    if (bridge == 0) {
        return;
    }

    bridge->listen_port = 5000;
    bridge->bluetooth_address = "00:00:00:00:00:00";
    bridge->bluetooth_channel = 1;
}

int mesh_emu_bridge_start(struct mesh_emu_bridge *bridge)
{
    int listen_socket;
    int reuse_address;
    struct sockaddr_in listen_address;

    if (bridge == 0) {
        return 1;
    }

    listen_socket = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_socket < 0) {
        mesh_emu_log_error("TCP socket creation failed");
        return 1;
    }

    reuse_address = 1;
    (void)setsockopt(listen_socket, SOL_SOCKET, SO_REUSEADDR, &reuse_address, sizeof(reuse_address));

    memset(&listen_address, 0, sizeof(listen_address));
    listen_address.sin_family = AF_INET;
    listen_address.sin_addr.s_addr = htonl(INADDR_ANY);
    listen_address.sin_port = htons((unsigned short)bridge->listen_port);

    if (bind(listen_socket, (struct sockaddr *)&listen_address, sizeof(listen_address)) != 0) {
        mesh_emu_log_error("TCP bind failed");
        close(listen_socket);
        return 1;
    }

    if (listen(listen_socket, 1) != 0) {
        mesh_emu_log_error("TCP listen failed");
        close(listen_socket);
        return 1;
    }

    mesh_emu_log_info("TCP server listening on port 5000");

    for (;;) {
        int client_socket;
        int bluetooth_socket;
        struct sockaddr_in client_address;
        socklen_t client_length;

        client_length = (socklen_t)sizeof(client_address);
        client_socket = accept(listen_socket, (struct sockaddr *)&client_address, &client_length);
        if (client_socket < 0) {
            if (errno == EINTR) {
                continue;
            }
            mesh_emu_log_error("TCP accept failed");
            close(listen_socket);
            return 1;
        }

        bluetooth_socket = mesh_emu_bridge_connect_to_bluetooth(bridge->bluetooth_address, bridge->bluetooth_channel);
        if (bluetooth_socket < 0) {
            mesh_emu_log_error("Bluetooth connection failed");
            close(client_socket);
            close(listen_socket);
            return 1;
        }

        mesh_emu_log_info("TCP client connected, forwarding to Bluetooth");
        if (mesh_emu_bridge_proxy_between_sockets(client_socket, bluetooth_socket) != 0) {
            mesh_emu_log_error("TCP to Bluetooth relay failed");
            close(bluetooth_socket);
            close(client_socket);
            close(listen_socket);
            return 1;
        }

        close(bluetooth_socket);
        close(client_socket);
    }
}

void mesh_emu_bridge_stop(struct mesh_emu_bridge *bridge)
{
    if (bridge == 0) {
        return;
    }

    mesh_emu_log_info("bridge stop placeholder for single-Pi relay");
}
