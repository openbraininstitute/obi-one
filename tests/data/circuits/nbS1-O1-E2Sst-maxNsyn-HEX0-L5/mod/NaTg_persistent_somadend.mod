:Reference :Colbert and Pan 2002

: Adapted by M. Zbili for Human cortex
: Adapted by Werner Van Geit @ BBP, 2015 (with help from M.Hines):
: channel detects TTX concentration set by TTXDynamicsSwitch.mod
: LJP: not corrected!

NEURON	{
	SUFFIX NaTg_persistent_somadend
	USEION na READ ena WRITE ina
	USEION ttx READ ttxo, ttxi VALENCE 1
	RANGE gNaTgbar, gNaTg, ina, vshiftm, slopem
}

UNITS	{
	(S) = (siemens)
	(mV) = (millivolt)
	(mA) = (milliamp)
}

PARAMETER	{
	gNaTgbar = 0.00001 (S/cm2)
	vshiftm = 1 (mV)
	slopem = 7
}

ASSIGNED	{
	ttxo (mM)
	ttxi (mM)
	v	(mV)
	ena	(mV)
	ina	(mA/cm2)
	gNaTg	(S/cm2)
	mInf
	mTau
	mAlpha
	mBeta
}

STATE	{
	m
}

BREAKPOINT	{
	SOLVE states METHOD cnexp
	gNaTg = gNaTgbar*m*m*m
	ina = gNaTg*(v-ena)
}

DERIVATIVE states	{
	if (ttxi == 0.015625 && ttxo > 1e-12) {
		mInf = 0.0
		mTau = 1e-12
	} else {
		rates()
	}
	m' = (mInf-m)/mTau
}

INITIAL{
	if (ttxi == 0.015625 && ttxo > 1e-12) {
		mInf = 0.0
		mTau = 1e-12
	} else {
		rates()
	}
	m = mInf
}

PROCEDURE rates(){
  LOCAL qt
  qt = 2.3^((34-21)/10)

  UNITSOFF
    if(v == (-38+vshiftm)){
    	v = v+0.0001
    }
		mAlpha = (0.182 * (v- (-38+vshiftm)))/(1-(exp(-(v- (-38+vshiftm))/slopem)))
		mBeta  = (0.124 * (-v + (-38+vshiftm)))/(1-(exp(-(-v + (-38+vshiftm))/slopem)))
		mTau = (1/(mAlpha + mBeta))/qt
		mInf = mAlpha/(mAlpha + mBeta)

	UNITSON
}
