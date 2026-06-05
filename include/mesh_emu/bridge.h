#ifndef MESH_EMU_BRIDGE_H
#define MESH_EMU_BRIDGE_H

struct mesh_emu_bridge {
    int listen_port;
    const char *bluetooth_address;
    int bluetooth_channel;
};

void mesh_emu_bridge_init(struct mesh_emu_bridge *bridge);
int mesh_emu_bridge_start(struct mesh_emu_bridge *bridge);
void mesh_emu_bridge_stop(struct mesh_emu_bridge *bridge);

#endif
