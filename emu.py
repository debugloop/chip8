import subprocess
import sys
import random
import time

import curses

from ui import CursesUI

class Chip8:
    pc = 0     # program counter
    opcode = 0 # current opcode
    sp = 0     # stack pointer

    stack = [0]*16    # 16 bytes of stack
    i = 0             # one special index register
    v = [0]*16        # 16 byte-size registers, called V
    memory = [0]*4096 # 4kB of memory
    memory[0:80] = [
        0xF0, 0x90, 0x90, 0x90, 0xF0, # 0
        0x20, 0x60, 0x20, 0x20, 0x70, # 1
        0xF0, 0x10, 0xF0, 0x80, 0xF0, # 2
        0xF0, 0x10, 0xF0, 0x10, 0xF0, # 3
        0x90, 0x90, 0xF0, 0x10, 0x10, # 4
        0xF0, 0x80, 0xF0, 0x10, 0xF0, # 5
        0xF0, 0x80, 0xF0, 0x90, 0xF0, # 6
        0xF0, 0x10, 0x20, 0x40, 0x40, # 7
        0xF0, 0x90, 0xF0, 0x90, 0xF0, # 8
        0xF0, 0x90, 0xF0, 0x10, 0xF0, # 9
        0xF0, 0x90, 0xF0, 0x90, 0x90, # A
        0xE0, 0x90, 0xE0, 0x90, 0xE0, # B
        0xF0, 0x80, 0x80, 0x80, 0xF0, # C
        0xE0, 0x90, 0x90, 0x90, 0xE0, # D
        0xF0, 0x80, 0xF0, 0x80, 0xF0, # E
        0xF0, 0x80, 0xF0, 0x80, 0x80] # F

    # 60Hz countdown timers
    delay_timer = 0
    sound_timer = 0
    cycles = 0

    def __init__(self, filename, ui, debug=False):
        self.debug = debug
        self.ui = ui
        self.pc = 0x200
        with open(filename, 'rb') as f:
            self.memory[0x200:] = f.read(4096)
        while len(self.memory) < 4096:
            self.memory.append(0)

    def clear_screen(self): # 0x00e0 cls
        self.ui.clear_screen()

    def return_from_subroutine(self): # 0x00ee rts
        self.sp -= 1
        self.pc = self.stack[self.sp]

    def jump(self): # 0x1NNN jmp NNN
        self.pc = self.opcode & 0x0fff;
        return "jmp 0x{:03X}".format(self.opcode & 0x0fff)

    def jump_to_subroutine(self): # 0x2NNN jsr NNN
        self.stack[self.sp] = self.pc
        self.sp += 1;
        self.pc = self.opcode & 0x0fff;
        return "jsr 0x{:03X}".format(self.opcode & 0x0fff)

    def skip_next_eq_const(self): # 0x3XRR skeq VX,RR
        if self.v[(self.opcode & 0x0f00) >> 8] == self.opcode & 0x00ff:
            self.pc += 2
        return "skeq V{:X},{}".format((self.opcode & 0x0f00) >> 8, self.opcode & 0x00ff)

    def skip_next_ne_const(self): # 0x4XRR skne VX,RR
        if self.v[(self.opcode & 0x0f00) >> 8] != self.opcode & 0x00ff:
            self.pc += 2
        return "skne V{:X},{}".format((self.opcode & 0x0f00) >> 8, self.opcode & 0x00ff)

    def skip_next_eq_reg(self): # 0x5XY0 skeq VX,VY
        if self.v[(self.opcode & 0x0f00) >> 8] == self.v[(self.opcode & 0x00f0) >> 4]:
            self.pc += 2
        return "skeq V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def load_const(self): # 0x6XRR mov VX,RR
        self.v[(self.opcode & 0x0f00) >> 8] = self.opcode & 0x00ff
        return "mov V{:X},{}".format((self.opcode & 0x0f00) >> 8, self.opcode & 0x00ff)

    def add_const(self): # 0x7XRR add VX,RR
        result = self.v[(self.opcode & 0x0f00) >> 8] + self.opcode & 0x00ff
        self.v[(self.opcode & 0x0f00) >> 8] = result & 0xffff
        return "add V{:X},{}".format((self.opcode & 0x0f00) >> 8, self.opcode & 0x00ff)

    def load_reg(self): # 0x8XY0 mov VX,VY
        self.v[(self.opcode & 0x0f00) >> 8] = self.v[(self.opcode & 0x00f0) >> 4]
        return "mov V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def or_reg(self): # 0x8XY1 or VX,VY
        self.v[(self.opcode & 0x0f00) >> 8] = ( self.v[(self.opcode & 0x0f00) >> 8] |
                                                self.v[(self.opcode & 0x00f0) >> 4] )
        return "or V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def and_reg(self): # 0x8XY2 and VX,VY
        self.v[(self.opcode & 0x0f00) >> 8] = ( self.v[(self.opcode & 0x0f00) >> 8] &
                                                self.v[(self.opcode & 0x00f0) >> 4] )
        return "and V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def xor_reg(self): # 0x8XY3 xor VX,VY
        self.v[(self.opcode & 0x0f00) >> 8] = ( self.v[(self.opcode & 0x0f00) >> 8] ^
                                                self.v[(self.opcode & 0x00f0) >> 4] )
        return "xor V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def add_reg(self): # 0x8XY4 add VX,VY
        result = self.v[(self.opcode & 0x0f00) >> 8] + self.v[(self.opcode & 0x00f0) >> 4]
        self.v[0xf] = result & 0xf0000
        self.v[(self.opcode & 0x0f00) >> 8] = result & 0xffff
        return "add V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def sub_reg(self): # 0x8XY5 sub VX,VY
        x = self.v[(self.opcode & 0x0f00) >> 8]
        y = self.v[(self.opcode & 0x00f0) >> 4]
        result = x - y
        self.v[0xf] = 1 if x > y else 0
        self.v[(self.opcode & 0x0f00) >> 8] = result & 0xff
        return "sub V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def shift_right(self): # 0x8X06 shr VX
        self.v[0xf] = self.v[(self.opcode & 0x0f00) >> 8] & 2**0
        self.v[(self.opcode & 0x0f00) >> 8] = self.v[(self.opcode & 0x0f00) >> 8] >> 1
        return "shr V{:X}".format((self.opcode & 0x0f00) >> 8)

    def shift_left(self): # 0x8X0e shl VX
        self.v[0xf] = self.v[(self.opcode & 0x0f00) >> 8] & 2**15
        self.v[(self.opcode & 0x0f00) >> 8] = (self.v[(self.opcode & 0x0f00) >> 8] << 1) & 0xffff
        return "shl V{:X}".format((self.opcode & 0x0f00) >> 8)

    def sub_reg_reverse(self): # 0x8XY7 rsb VX,VY
        x = self.v[(self.opcode & 0x0f00) >> 8]
        y = self.v[(self.opcode & 0x00f0) >> 4]
        result = y - x
        self.v[0xf] = 1 if y > x else 0
        self.v[(self.opcode & 0x0f00) >> 8] = result & 0xff
        return "rsb V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def skip_next_ne_reg(self): # 0x9XY0 skne VX,VY
        if self.v[(self.opcode & 0x0f00) >> 8] != self.v[(self.opcode & 0x00f0) >> 4]:
            self.pc += 2
        return "skne V{:X},V{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4)

    def load_const_i(self): # 0xaNNN mvi NNN
        self.i = self.opcode & 0x0fff
        return "mvi 0x{:03X}".format(self.opcode & 0x0fff)

    def jump_i(self): # 0xbNNN jmi NNN
        self.pc = (self.opcode & 0x0fff) + self.v[0];
        return "jmi 0x{:03X}".format(self.opcode & 0x0fff)

    def load_random(self): # 0xcXKK rand VX,KK
        self.v[(self.opcode & 0x0f00) >> 8] = random.randint(0, 2**15) & (self.opcode & 0x00ff)
        return "rand V{:X},0x{:02X}".format((self.opcode & 0x0f00) >> 8, self.opcode & 0x00ff)

    def draw_sprite(self): # 0xdXYN sprite VX,VY,N (n = 0 -> 16)
        x = self.v[(self.opcode & 0x0f00) >> 8]
        y = self.v[(self.opcode & 0x00f0) >> 4]
        n = self.opcode & 0x000f
        self.v[0x000f] = 0 # no collision, yet
        if n == 0:
            n = 16
        for yline in range(n):
            value = self.memory[self.i + yline]
            for xline in range(8):
                if (value & (0x80 >> xline)) != 0:
                    if self.ui.get_pixel(x+xline, y+yline):
                        self.v[0x000f] = 1
                    self.ui.toggle_pixel(x+xline, y+yline)
        return "sprite V{:X},V{:X},0x{:X}".format((self.opcode & 0x0f00) >> 8, (self.opcode & 0x00f0) >> 4, self.opcode & 0x000f)

    def get_delay(self): # 0xfR07 gdelay VR
        self.v[(self.opcode & 0x0f00) >> 8] = self.delay_timer
        return "gdelay 0x{:X}".format((self.opcode & 0x0f00) >> 8)

    def wait_key(self): # 0xfR0a key VR
        self.v[(self.opcode & 0x0f00) >> 8] = self.ui.wait_key()
        return "key V{:X}".format((self.opcode & 0x0f00) >> 8)

    def set_delay_timer(self): # 0xfR15 sdelay VR
        self.delay_timer = self.v[(self.opcode & 0x0f00) >> 8]
        return "sdelay V{:X}".format((self.opcode & 0x0f00) >> 8)

    def set_sound_timer(self): # 0xfR18 ssound VR
        self.sound_timer = self.v[(self.opcode & 0x0f00) >> 8]
        return "ssound V{:X}".format((self.opcode & 0x0f00) >> 8)

    def skip_keydown(self): # 0xeK9e skpr K
        k = self.v[(self.opcode & 0x0f00) >> 8]
        if self.ui.get_key(k):
            self.pc += 2
        return "skpr 0x{:X}".format((self.opcode & 0x0f00) >> 8)

    def skip_keyup(self): # 0xeKa1 skup K
        k = self.v[(self.opcode & 0x0f00) >> 8]
        if not self.ui.get_key(k):
            self.pc += 2
        return "skup 0x{:X}".format((self.opcode & 0x0f00) >> 8)

    def add_to_i(self): # 0xfR1e adi VR
        self.i = self.i + self.v[(self.opcode & 0x0f00) >> 8]
        return "adi V{:X}".format((self.opcode & 0x0f00) >> 8)

    def set_char(self): # 0xfR29 font VR
        r = self.v[(self.opcode & 0x0f00) >> 8]
        self.i = r*5
        return "font V{:X}".format((self.opcode & 0x0f00) >> 8)

    def put_bcd(self): # 0xfR33 bcd VR
        self.memory[self.i] = int(self.v[((self.opcode & 0x0f00) >> 8)] / 100)
        self.memory[self.i+1] = int((self.v[((self.opcode & 0x0f00) >> 8)] / 10) % 10)
        self.memory[self.i+2] = int((self.v[((self.opcode & 0x0f00) >> 8)] % 100) % 10)
        return "bcd V{:X}".format((self.opcode & 0x0f00) >> 8)

    def store_reg_to_mem(self): # 0xfR55 str V0-VR
        r = (self.opcode & 0x0f00) >> 8
        for reg in range(r+1):
            self.memory[self.i+reg] = self.v[reg]
        return "str V{:X}".format((self.opcode & 0x0f00) >> 8)

    def load_reg_from_mem(self): # 0xfR65 ldr V0-VR
        r = (self.opcode & 0x0f00) >> 8
        for reg in range(r+1):
            self.v[reg] = self.memory[self.i+reg]
        return "ldr V{:X}".format((self.opcode & 0x0f00) >> 8)

    op_map = {
            0x00e0: ("cls", clear_screen),              # 0x00e0 cls
            0x00ee: ("rts", return_from_subroutine),    # 0x00ee rts
            0x1000: ("jmp NNN", jump),                  # 0x1NNN jmp NNN
            0x2000: ("jsr NNN", jump_to_subroutine),    # 0x2NNN jsr NNN
            0x3000: ("skeq VX,RR", skip_next_eq_const), # 0x3XRR skeq VX,RR
            0x4000: ("skne VX,RR", skip_next_ne_const), # 0x4XRR skne VX,RR
            0x5000: ("skeq VX,VY", skip_next_eq_reg),   # 0x5XY0 skeq VX,VY
            0x6000: ("mov VX,RR", load_const),          # 0x6XRR mov VX,RR
            0x7000: ("add VX,RR", add_const),           # 0x7XRR add VX,RR
            0x8000: ("mov VX,VY", load_reg),            # 0x8XY0 mov VX,VY
            0x8001: ("or VX,VY", or_reg),               # 0x8XY1 or VX,VY
            0x8002: ("and VX,VY", and_reg),             # 0x8XY2 and VX,VY
            0x8003: ("xor VX,VY", xor_reg),             # 0x8XY3 xor VX,VY
            0x8004: ("add VX,VY", add_reg),             # 0x8XY4 add VX,VY
            0x8005: ("sub VX,VY", sub_reg),             # 0x8XY5 sub VX,VY
            0x8006: ("shr VX", shift_right),            # 0x8X06 shr VX
            0x8007: ("rsb VX,VY", sub_reg_reverse),     # 0x8XY7 rsb VX,VY
            0x800e: ("shl VX", shift_left),             # 0x8X0e shl VX
            0x9000: ("skne VX,VY", skip_next_ne_reg),   # 0x9XY0 skne VX,VY
            0xa000: ("mvi NNN", load_const_i),          # 0xaNNN mvi NNN
            0xb000: ("jmi NNN", jump_i),                # 0xbNNN jmi NNN
            0xc000: ("rand VX,KK", load_random),        # 0xcXKK rand VX,KK
            0xd000: ("sprite VX,VY,N", draw_sprite),    # 0xdXYN sprite VX,VY,N
            0xe09e: ("skpr K", skip_keydown),           # 0xeK9e skpr K
            0xe0a1: ("skup K", skip_keyup),             # 0xeKa1 skup K
            0xf007: ("gdelay VR", get_delay),           # 0xfR07 gdelay VR
            0xf00a: ("key VR", wait_key),               # 0xfR0a key VR
            0xf015: ("sdelay VR", set_delay_timer),     # 0xfR15 sdelay VR
            0xf018: ("ssound VR", set_sound_timer),     # 0xfR18 ssound VR
            0xf01e: ("adi VR", add_to_i),               # 0xfR1e adi VR
            0xf029: ("font VR", set_char),              # 0xfR29 font VR
            0xf033: ("bcd VR", put_bcd),                # 0xfR33 bcd VR
            0xf055: ("str V0-VR", store_reg_to_mem),    # 0xfR55 str V0-VR
            0xf065: ("ldr V0-VR", load_reg_from_mem),   # 0xfR65 ldr V0-VR
            }

    def cycle(self):
        # fetch an opcode
        current_pc = self.pc # save unmodified pc for printing correct mem location
        self.pc += 2

        self.opcode = self.memory[current_pc] << 8 | self.memory[current_pc + 1]

        try: # decode an opcode
            mask = 0xf000 # the first nibble is enough most of the time

            # extend the mask if necessary
            if self.opcode & 0xf000 == 0x8000:
                mask = 0xf00f
            elif self.opcode & 0xf000 in [0x0000, 0xe000, 0xf000]:
                mask = 0xf0ff

            # get a descriptive string (no params decoded) and the proper function
            op_str, op_func = self.op_map[self.opcode & mask]
        except KeyError:
            # indicates a buggy program or the pc running into uninitialized memory
            self.ui.update_code_window(current_pc, "TERMINATION")
            return False

        if op_func: # indicated an implemented op code
            decoded = op_func(self) # get a new descriptive string with decoded params
            if decoded:
                op_str = decoded
            self.ui.update_code_window(current_pc, op_str) # print decoded instruction with params
        else:
            self.ui.update_code_window(current_pc, "*{}*".format(op_str)) # print unimplemented instruction

        # insert space into code listing if a jump occured
        if current_pc != self.pc-2:
            self.ui.update_code_window()

        # update currently set variables
        self.ui.update_var_window(self)

        # sleep to prevent too fast execution
        if self.debug:
            self.ui.wait_key()
        else:
            time.sleep(1/300)

        # handle timers with 60Hz
        self.cycles += 1
        if self.cycles >= 5:
            self.ui.screen_redraw() # redraw screen too, while we're at it

            if self.delay_timer > 0: # for use by programs, do nothing
                self.delay_timer -= 1

            if self.sound_timer > 0: # beep upon reaching zero
                self.sound_timer -= 1
                if self.sound_timer == 0:
                    subprocess.Popen(["aplay", "beep.wav"], stderr=subprocess.DEVNULL)

        return True

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument('-d', help='Debug by stepping through ROM.', action='store_true')
    args = parser.parse_args()

    ui = curses.wrapper(CursesUI)
    myChip8 = Chip8(args.filename, ui, debug=args.d)

    try:
        while myChip8.cycle():
            pass
    except KeyboardInterrupt:
        time.sleep(1)
        ui.exit()
