// Lebai gripper probe via xArm C++ SDK tool RS485
// Read CUR_POSITION (0x9C45) from slave 1 @ 115200, host_id=9 (tool end)
#include <cstdio>
#include <cstring>
#include "xarm/wrapper/xarm_api.h"

int main(int argc, char **argv) {
    const char *ip = argc > 1 ? argv[1] : "192.168.23.227";
    XArmAPI *arm = new XArmAPI(ip);
    if (!arm->is_connected()) { printf("not connected\n"); return 1; }

    int ret = arm->set_tgpio_modbus_baudrate(115200);
    printf("set baud: %d\n", ret);
    sleep_milliseconds(2000);

    // FC03 read holding register 0x9C45, count 1 (no CRC — controller adds it)
    unsigned char tx[6] = {0x01, 0x03, 0x9C, 0x45, 0x00, 0x01};
    unsigned char rx[256] = {0};

    for (int attempt = 0; attempt < 3; attempt++) {
        memset(rx, 0, sizeof(rx));
        ret = arm->getset_tgpio_modbus_data(tx, 6, rx, sizeof(rx), 9);
        printf("attempt %d: code=%d err=%d rx=[", attempt, ret, arm->error_code);
        int n = 0;
        for (int i = 0; i < 32; i++) { if (rx[i]) n = i + 1; }
        for (int i = 0; i < (n ? n : 8); i++) printf("%02X ", rx[i]);
        printf("]\n");
        if (arm->error_code) arm->clean_error();
        sleep_milliseconds(500);
    }

    delete arm;
    return 0;
}
