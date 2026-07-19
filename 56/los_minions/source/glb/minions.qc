// QC for Los Minions — compile after exporting SMD/DMX from minions.glb
// Output: models/los_minions/minions.mdl

$modelname "los_minions/minions.mdl"
$cdmaterials "los_minions/"

$scale 1.0
$staticprop

$body "body" "minions.smd"

$sequence idle "minions.smd" loop fps 30
$sequence walk "minions.smd" loop fps 30
$sequence run "minions.smd" loop fps 30

$collisionmodel "minions.smd"
{
	$mass 80
	$concave
}
