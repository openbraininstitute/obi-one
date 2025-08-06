:Reference :Battefeld et al., J.Neuroscience, 2014

: Adapted by Mickael Zbili @ BBP, 2020:
: LJP: corrected in the paper
: Temperature of recordings: 35 celsius (no qt described in the model)
: ntau has been modified (error in the fitting equation of the paper)

NEURON	{
	SUFFIX Kv7
	USEION k READ ek WRITE ik
	RANGE gKv7bar, gKv7, ik
}

UNITS	{
	(S) = (siemens)
	(mV) = (millivolt)
	(mA) = (milliamp)
}

PARAMETER	{
	gKv7bar = 0.00001 (S/cm2)
}

ASSIGNED	{
	v	(mV)
	ek	(mV)
	ik	(mA/cm2)
	gKv7	(S/cm2)
	ninf
	ntau (ms)
	nalpha (1/ms)
	nbeta (1/ms)
}

STATE	{
	n
}

BREAKPOINT	{
	SOLVE states METHOD cnexp
	gKv7 = gKv7bar*n
	ik = gKv7*(v-ek)
}

DERIVATIVE states	{
	rates()
	n' = (ninf-n)/ntau
}

INITIAL{
	rates()
	n = ninf
}

PROCEDURE rates(){

  UNITSOFF
	nalpha = 0.036*exp(0.909*v/26.55)
	nbeta = 0.002*exp(-1.102*v/26.55)
	ninf = nalpha/(nalpha+nbeta) 
	ntau = 1/(nalpha + nbeta)
	UNITSON
}
