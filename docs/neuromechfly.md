---
tags:
  - circuit-simulation
---

# Brian2 NeuroMechFly Closed-Loop Simulations

A Brian2 point-neuron circuit can be wired to the NeuroMechFly body ([flygym](https://github.com/NeLy-EPFL/flygym) 1.2.1) as a fly's nervous system is wired to its body:

- odours reach the circuit only through its olfactory receptor neurons, each firing for the odour at its own antenna or maxillary palp;
- the legs move only as the circuit's leg motor neurons drive their muscles;
- the circuit's leg proprioceptors and bristles feel the joints and the floor.

There is no stepping controller, steering rule or valence readout. If the fly walks, or turns towards an odour, its circuit makes it do so; a circuit that cannot will make the fly do something else, and that is the model's answer.

Which neurons the body drives and reads, and how, is part of the model, so the **circuit** carries it as its body interface. The simulation is the experiment: the arena and what is done to the body. Campaigns are configured with `Brian2NeuroMechFlySimulationScanConfig` (generate endpoint `/generated/brian-2-neuro-mech-fly-simulation-scan-config-generate-grid`), which writes a `neuromechfly` section into `simulation_config.json`. A Brian2 simulation with that section is launched as `circuit_simulation_neuromechfly_machine`, which runs `obi_one/scientific/library/simulation/neuromechfly/simulate_neuromechfly.py`.

## The circuit's body interface

Node properties place each neuron in the body (`obi_one.scientific.library.simulation.neuromechfly.interface`):

- `body_input` names the sense a sensory neuron carries:
  - `odour/<antenna|maxillary_palp>/<left|right>/<class>`: an olfactory receptor neuron of an odour class (`yeasty_volatile`, `fruity_volatile`, `carbon_dioxide_volatile`, ...);
  - `chordotonal/<leg>/<claw|hook|club>`: a femoral chordotonal neuron of leg `LF` ... `RH`;
  - `hair_plate/<leg>/<coxa|trochanter>`, `campaniform/<leg>` and `touch/<leg>` for hair plates, campaniform sensilla and leg bristles.
- `body_output` names the muscle a motor neuron drives: `muscle/<leg>/<muscle>`, e.g. `muscle/LF/tibia_flexor_muscle`.
- `body_tuning` holds a number some senses need per neuron: a claw neuron's preferred tibia angle (radians), a hook neuron's direction (+1 flexion, -1 extension).

Neurons outside the interface hold the fill value. `components.body_interface_file` in `circuit_config.json` names a JSON file (`BodyInterface`, version 2) with:

- `muscles`: for each leg, what each muscle does: shares of its torque on flygym's actuated joints (`Coxa`, `Coxa_roll`, `Coxa_yaw`, `Femur`, `Femur_roll`, `Tibia`, `Tarsus1`, signed by direction), or the leg's grip (`grip`, for the long tendon muscle);
- `motor`: the muscles' saturation rate, activation time constant and strength, and the joints' passive stiffness towards the standing pose and damping;
- `sensing`: each sense's transfer function from the body's state to firing rate;
- optional `placement`, a 4x4 matrix from circuit µm to the body's frame in mm, which the web app uses to draw the circuit inside the fly; the simulation ignores it.

A circuit without the interface is refused when the campaign is generated, and one with an interface of the earlier, hand-made rules (version 1) is refused when it runs.

## The loop

The network runs at 0.1 ms, as in Shiu et al. The body (0.1 ms physics steps) and the network run together from the start, and exchange every `coupling_step` (1 ms) inside the network's run:

1. Muscles: each muscle's activation follows the mean firing rate of its motor neurons, with a 20 ms time constant, full at 100 Hz. Its torque is its strength (20 µN·mm by default) times its activation, on each joint it acts on. A joint's torques are capped at 65 µN·mm together.
2. The body moves for the coupling step under those torques, the joints' passive springs (20 µN·mm/radian towards the standing pose, by default) and damping, gravity, contacts, and the experiment's pushes and leg overrides.
3. Senses: each sensory neuron gets Poisson input at the rate its sense sets, and each event fires it (68.75 mV, no refractory period):
   - an odour receptor neuron: spontaneous 2 Hz up to 200 Hz, a Hill function of the intensity of its class at its own organ (half at 0.02, with sources falling off with the inverse square of distance);
   - a claw neuron: a Gaussian of its tibia's angle around its preferred angle (sigma 0.25 radian);
   - a hook neuron: its tibia's angular velocity in its direction, saturating at 10 radian/s;
   - a club neuron: its tibia's angular acceleration, either way;
   - a hair plate neuron: its joint's deflection from the standing pose;
   - a campaniform sensillum neuron: the load on its leg (its contact forces);
   - a bristle neuron: the change of its leg's contact forces; bristles adapt, so steady contact leaves them quiet.

The run lasts `tstop`. A physics fault (the body falling apart) stops the body there; the network runs on.

## Blocks

The config is UI-enabled; its closed-loop blocks form the **Body** group:

- **Arena**: peak odour intensity, capture radius (for noting when the fly reaches a source) and start heading. The fly starts at the origin, facing +X, standing.
- **Odour sources** (at least one): `x`, `y` in mm and the odour's class, which decides the receptor neurons it drives. A source keeps emitting once reached.
- **Walls**: `(x0, y0)` to `(x1, y1)` in mm, boxes 1.2 mm thick and 3 mm high.
- **Body forces**: pushes on the thorax, head, abdomen or one leg (at its tibia), in µN; the fly weighs about 10 µN. A force's axes are the fly's forward, left and up (turning with its heading, not its pitch or roll) or the arena's. It is steady, or a sine at its frequency, from its start for its duration.
- **Leg overrides**: one leg taken from its muscles for a window, as if held by hand (gains of 45 µN·mm/radian, cancelling the passive springs): **hold** freezes it as it is (a planted foot keeps its grip), **lift** raises it about 1 mm off the floor (the femur raised 69 degrees from the standing pose), **limp** cuts its muscles, leaving only the passive springs, and **swing** holds it while one joint swings as a sine. Where two overrides take the same leg at once, the later one wins.

Forces and leg overrides are timed in ms from the start of the simulation. Stimuli, recordings and manipulations (e.g. a lesion as a synaptic manipulation) work as in any Brian2 simulation, on the same clock.

## Outputs

The spikes are written and registered as in any Brian2 simulation. The spikes file also holds a `neuromechfly` group: one dataset per trajectory column, every 10 ms (time, position, heading, sources reached, whether a push or leg override acted, and whether the fly is right side up), and a `summary` attribute (sources reached and when, when the fly first turned over if it did, path length, straightness, speed). A `neuromechfly_replay` dataset (JSON text, also written beside the spikes file as `neuromechfly_replay.json`) holds the body's every joint and pose every 10 ms, for replaying the episode in 3D. The registered spike report carries it, since a simulation result's assets can only be h5 reports.

## Running it locally

flygym is installed by the launch job, not with obi-one. In an environment with obi-one and `flygym==1.2.1`:

```bash
python obi_one/scientific/library/simulation/neuromechfly/simulate_neuromechfly.py \
    sonata-simulation --simulation-path simulation_config.json -v
```

## Limitations

- No vision: photoreceptors get no input, and walls are physical obstacles only.
- The head, antennae, wings, halteres and abdomen do not move, so their sensory neurons (Johnston's organ, wing and haltere sensors) get no input and their motor neurons drive nothing.
- Where the annotation does not say, the interface assumes: which hook neurons are flexion- or extension-selective, each claw neuron's preferred angle, and the joint of a hair plate (the coxa, unless it names the trochanter). The circuit's body interface records these choices per neuron, so they can be changed.
- A muscle acts on one joint (two for the pleural remotor and abductor), in the direction its annotated function names; moment arms and muscle force-length properties are not modelled.
- Billed as a Brian2 circuit simulation.
