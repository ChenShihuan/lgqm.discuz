package Git::Mediawiki;

use 5.008;
use strict;
use POSIX;
use Git;
use Encode;

BEGIN {

our ($VERSION, @ISA, @EXPORT, @EXPORT_OK);

$VERSION = '0.01';

require Exporter;

@ISA = qw(Exporter);

@EXPORT = ();

@EXPORT_OK = qw(clean_filename smudge_filename connect_maybe
				EMPTY HTTP_CODE_OK HTTP_CODE_PAGE_NOT_FOUND);
}

use constant SLASH_REPLACEMENT => '%2F';
use constant EMPTY => q{};
use constant HTTP_CODE_OK => 200;
use constant HTTP_CODE_PAGE_NOT_FOUND => 404;

sub clean_filename {
	my $filename = shift;
	$filename =~ s{@{[SLASH_REPLACEMENT]}}{/}g;
	$filename =~ s/[\[\]\{\}\|]/sprintf("_%%_%x", ord($&))/ge;
	return $filename;
}

sub smudge_filename {
	my $filename = shift;
	$filename =~ s{/}{@{[SLASH_REPLACEMENT]}}g;
	$filename =~ s/ /_/g;
	$filename =~ s/_%_([0-9a-fA-F][0-9a-fA-F])/sprintf('%c', hex($1))/ge;
	return substr($filename, 0, NAME_MAX-length('.mw'));
}

sub connect_maybe {
	my $wiki = shift;
	if ($wiki) {
		return $wiki;
	}

	my $remote_name = shift;
	my $remote_url = shift;
	my ($wiki_login, $wiki_password, $wiki_domain);

	$wiki_login = Git::config("remote.${remote_name}.mwLogin");
	$wiki_password = Git::config("remote.${remote_name}.mwPassword");
	$wiki_domain = Git::config("remote.${remote_name}.mwDomain");

	# Git::config returns raw bytes; decode UTF-8 for non-ASCII usernames
	$wiki_login = Encode::decode('UTF-8', $wiki_login) if defined $wiki_login;
	$wiki_password = Encode::decode('UTF-8', $wiki_password) if defined $wiki_password;

	$wiki = MediaWiki::API->new;
	$wiki->{config}->{api_url} = "${remote_url}/api.php";

	# X-authkey header MUST be set before login
	my $mw_auth_key = Git::config("remote.${remote_name}.mwAuthKey");
	if ($mw_auth_key) {
		$wiki->{ua}->default_header('X-authkey' => $mw_auth_key);
	}

	if ($wiki_login) {
		my $request = {lgname => $wiki_login,
			       lgpassword => $wiki_password,
			       lgdomain => $wiki_domain};
		if ($wiki->login($request)) {
			print {*STDERR} qq(Logged in as "$wiki_login".\n);
		} else {
			print {*STDERR} qq(Login failed: ) . $wiki->{error}->{details} . "\n";
			if (!$mw_auth_key) {
				exit 1;
			}
			print {*STDERR} "Continuing with X-authkey only.\n";
		}
	}

	return $wiki;
}

1;
