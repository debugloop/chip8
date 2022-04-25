import sys
import curses
from collections import defaultdict, deque

SCREEN_W = 64
SCREEN_H = 32

SIDEPANE_W = CODE_W = VAR_W = 32
CODE_H = 21
VAR_H = 10

assert SCREEN_H == (CODE_H + VAR_H + 1)

WINDOW_W = SCREEN_W + SIDEPANE_W
WINDOW_H = SCREEN_H

# 1 2 3 C
# 4 5 6 D
# 7 8 9 E
# A 0 B F
KEYMAP = { 0x0: ord('x'), 0x1: ord('1'), 0x2: ord('2'), 0x3: ord('3'),
           0x4: ord('q'), 0x5: ord('w'), 0x6: ord('e'), 0x7: ord('a'),
           0x8: ord('s'), 0x9: ord('d'), 0xa: ord('z'), 0xb: ord('c'),
           0xc: ord('4'), 0xd: ord('r'), 0xe: ord('f'), 0xf: ord('v')}
INV_KEYMAP = {v: k for k, v in KEYMAP.items()}

class CursesUI:
    def __init__(self, stdscr):
        self.screen_contents = set()
        self.code_contents = deque([], CODE_H)
        self.lastpressed = 0

        self.stdscr = stdscr

        curses.curs_set(False)
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)

        self.stdscr.keypad(1)
        self.stdscr.timeout(0)

        self.full_redraw()

    def exit(self):
        self.stdscr.refresh()
        curses.endwin()

    def wait_key(self):
        self.stdscr.timeout(1)
        while True:
            key = self.stdscr.getch(self.var_y, self.var_x+VAR_W-1)
            self.stdscr.addstr(self.var_y, self.var_x+VAR_W-1, " ")
            if key == curses.ERR or key not in INV_KEYMAP.keys():
                continue
            self.stdscr.timeout(0)
            return INV_KEYMAP[key]

    def get_key(self, k):
        state = self.lastpressed == KEYMAP[k]
        if state:
            self.lastpressed = 0
        return state

    def clear_screen(self):
        self.screen_contents = set()
        self.screen_redraw()

    def toggle_pixel(self, x, y):
        self.screen_contents = self.screen_contents ^ {(x, y)}

    def get_pixel(self, x, y):
        return (x, y) in self.screen_contents

    def update_code_window(self, pc=None, op=None):
        if not pc or not op:
            newline = " "*(CODE_W-1)
        else:
            newline = "0x{:04X}:{}{:>16}".format(pc, " "*(CODE_W-16-6-2-1), op)
        self.code_contents.append(newline)
        for i, line in enumerate(range(self.code_y, self.code_y+22)):
            try:
                text = self.code_contents[i]
                if "TERMINATION" in text:
                    self.stdscr.addstr(line, self.code_x+1, self.code_contents[i], curses.color_pair(1))
                elif i == 21:
                    self.stdscr.addstr(line, self.code_x+1, self.code_contents[i], curses.color_pair(2))
                else:
                    self.stdscr.addstr(line, self.code_x+1, self.code_contents[i])
            except IndexError:
                self.stdscr.chgat(line-1, self.code_x+1, CODE_W-2, curses.color_pair(2))
                break
        self.stdscr.refresh()

    def update_var_window(self, obj):
        self.stdscr.addstr(self.var_y, self.var_x+6, "0x{:04X}".format(obj.pc))
        self.stdscr.addstr(self.var_y+1, self.var_x+6, "0x{:04X}".format(obj.i))
        self.stdscr.addstr(self.var_y+1, self.var_x+int(VAR_W/2)+5, "0x{:04X}".format(obj.sp))
        for val, line in enumerate(range(self.var_y+2, self.var_y+10)):
            self.stdscr.addstr(line, self.var_x+6, "0x{:04X}".format(obj.v[val]))
            self.stdscr.addstr(line, self.var_x+int(VAR_W/2)+5, "0x{:04X}".format(obj.v[val+8]))
        self.stdscr.refresh()

    def screen_redraw(self):
        if (self.height, self.width) != self.stdscr.getmaxyx():
            self.full_redraw()
        for x in range(SCREEN_W):
            for y in range(SCREEN_H):
                pixel = '█' if (x, y) in self.screen_contents else ' '
                self.stdscr.addstr(self.screen_y+y, self.screen_x+x, pixel, curses.color_pair(1))
        self.stdscr.refresh()
        key = self.stdscr.getch(self.var_y, self.var_x+VAR_W-1)
        self.stdscr.addstr(self.var_y, self.var_x+VAR_W-1, " ")
        self.lastpressed = key if key != -1 else self.lastpressed

    def full_redraw(self):
        self.stdscr.clear()

        # center screen
        self.height, self.width = self.stdscr.getmaxyx()

        # calculate window roots
        self.screen_y = int((self.height - WINDOW_H) / 2)
        self.screen_x = int((self.width - WINDOW_W) / 2)
        self.code_y = self.screen_y
        self.code_x = self.screen_x + SCREEN_W + 1
        self.var_y = self.code_y + CODE_H + 1
        self.var_x = self.code_x

        # draw frames
        try:
            aux_wins = self.stdscr.derwin(SCREEN_H+2, SCREEN_W+2, self.screen_y-1, self.screen_x-1), \
                          self.stdscr.derwin(CODE_H+2, CODE_W+2, self.code_y-1, self.code_x-1), \
                          self.stdscr.derwin(VAR_H+2, VAR_W+2, self.var_y-1, self.var_x-1)
            for win in aux_wins:
                win.border()
                win.refresh()
            del aux_wins
        except curses.error:
            self.exit()
            print("Window to small...")
            sys.exit(1)

        self.stdscr.addstr(self.code_y-1, self.var_x-1, '┬')
        self.stdscr.addstr(self.var_y-1, self.var_x-1, '├')
        self.stdscr.addstr(self.var_y-1, self.var_x+VAR_W, '┤')
        self.stdscr.addstr(self.var_y+VAR_H, self.var_x-1, '┴')

        self.stdscr.addstr(self.var_y, self.var_x+1, 'PC:')
        self.stdscr.addstr(self.var_y+1, self.var_x+1, ' I:')
        self.stdscr.addstr(self.var_y+1, self.var_x+int(VAR_W/2), 'SP:')
        for val, line in enumerate(range(self.var_y+2, self.var_y+10)):
            self.stdscr.addstr(line, self.var_x+1, 'V{:X}:'.format(val))
            self.stdscr.addstr(line, self.var_x+int(VAR_W/2), 'V{:X}:'.format(val+8))

        self.stdscr.refresh()
