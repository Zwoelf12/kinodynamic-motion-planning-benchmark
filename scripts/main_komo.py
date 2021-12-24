import numpy as np
import yaml
import argparse
import tempfile
from pathlib import Path
import subprocess

import robots
import translate_g
import yaml_to_plain

def run_komo(filename_env, filename_initial_guess, filename_result):

	with tempfile.TemporaryDirectory() as tmpdirname:
		p = Path(tmpdirname)
		# convert environment YAML -> g
		filename_g = p / "env.g"
		translate_g.write(filename_env, str(filename_g))

		# convert initial guess yaml -> txt
		filename_guess = p / "initial_guess.txt"
		yaml_to_plain.write(filename_initial_guess, filename_guess)

		# Run KOMO
		filename_out = p / "out.txt"
		result = subprocess.run(["./rai_dubins",
				"-model", "\""+str(filename_g)+"\"",
				"-waypoints", "\""+str(filename_guess)+"\"",
				"-one_every", "1",
				"-display", str(0),
				"-animate", str(0),
				"-out", "\""+str(filename_out)+"\""])
		if result.returncode != 0:
			print("KOMO failed")
			return False
		else:
			# convert txt -> yaml
			data = np.loadtxt(filename_out, ndmin=2)
			result = {"result": [{"states": data.tolist()}]}
			with open(filename_result, 'w') as f:
				yaml.dump(result, f)
			return True


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("env", help="file containing the environment (YAML)")
	parser.add_argument("initial_guess", help="file containing the initial_guess (e.g., from db-A*) (YAML)")
	parser.add_argument("result", help="file containing the optimization result (YAML)")
	args = parser.parse_args()

	run_komo(args.env, args.initial_guess, args.result)


if __name__ == '__main__':
	main()
