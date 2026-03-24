import 'dart:convert';
import 'dart:ui';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/foundation.dart'; // For kIsWeb
import 'package:file_saver/file_saver.dart';

void main() {
  runApp(const CareerLensApp());
}

class CareerLensApp extends StatelessWidget {
  const CareerLensApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CareerLens AI',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4), // Primary purple
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        fontFamily: 'Roboto',
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFD0BCFF), // Light purple for dark mode
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        fontFamily: 'Roboto',
      ),
      themeMode: ThemeMode.system,
      home: const CareerLensHome(),
    );
  }
}

class CareerLensHome extends StatefulWidget {
  const CareerLensHome({super.key});

  @override
  State<CareerLensHome> createState() => _CareerLensHomeState();
}

class _CareerLensHomeState extends State<CareerLensHome> with SingleTickerProviderStateMixin {
  final TextEditingController _resumeController = TextEditingController();
  final TextEditingController _jobDescController = TextEditingController();
  final TextEditingController _apiKeyController = TextEditingController();
  
  bool _isLoading = false;
  String? _generatedHtml;
  String _apiStatus = "Checking API...";

  static const String _resumePrefKey = "saved_master_resume";
  static const String _apiPrefKey = "saved_api_key";
  
  String get _backendUrl {
    if (kIsWeb) {
      return "${Uri.base.origin}/api/v1";
    } else if (defaultTargetPlatform == TargetPlatform.android) {
      return "http://10.0.2.2:8000/api/v1";
    }
    return "http://127.0.0.1:8000/api/v1";
  }

  // Animation controller for soft UI effects
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this, 
      duration: const Duration(milliseconds: 800)
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animationController, 
      curve: Curves.decelerate
    );
    _animationController.forward();
    
    _loadSavedResume();
    _checkApiHealth();
  }

  @override
  void dispose() {
    _animationController.dispose();
    _resumeController.dispose();
    _jobDescController.dispose();
    _apiKeyController.dispose();
    super.dispose();
  }

  Future<void> _loadSavedResume() async {
    final prefs = await SharedPreferences.getInstance();
    final savedResume = prefs.getString(_resumePrefKey);
    final savedApiKey = prefs.getString(_apiPrefKey);
    
    setState(() {
      if (savedResume != null && savedResume.isNotEmpty) _resumeController.text = savedResume;
      if (savedApiKey != null && savedApiKey.isNotEmpty) _apiKeyController.text = savedApiKey;
    });
  }

  Future<void> _saveResume(String resumeText) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_resumePrefKey, resumeText);
    await prefs.setString(_apiPrefKey, _apiKeyController.text.trim());
  }

  Future<void> _checkApiHealth() async {
    String healthUrl = "$_backendUrl/health";

    try {
      final response = await http.get(Uri.parse(healthUrl)).timeout(const Duration(seconds: 3));
      if (response.statusCode == 200) {
        setState(() {
          _apiStatus = "API Connected";
        });
      } else {
        setState(() {
          _apiStatus = "API Error: \${response.statusCode}";
        });
      }
    } catch (e) {
      setState(() {
        _apiStatus = "API Offline";
      });
    }
  }

  Future<void> _generateCareerData() async {
    if (_resumeController.text.trim().isEmpty || _jobDescController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Please provide both Master Resume and Job Description'),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );
      return;
    }

    setState(() {
      _isLoading = true;
      _generatedHtml = null;
    });

    await _saveResume(_resumeController.text);

    String generateUrl = "$_backendUrl/generate";

    try {
      final response = await http.post(
        Uri.parse(generateUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'job_description': _jobDescController.text.trim(),
          'master_resume': _resumeController.text.trim(),
          if (_apiKeyController.text.trim().isNotEmpty) 'user_api_key': _apiKeyController.text.trim(),
        }),
      );

      if (response.statusCode == 200) {
        setState(() {
          _generatedHtml = response.body;
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text('Template Successfully Generated!'),
              behavior: SnackBarBehavior.floating,
              backgroundColor: Theme.of(context).colorScheme.primary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          );
        }
      } else {
        if (mounted) {
          String errorMessage = 'Generation Failed: \${response.statusCode}';
          try {
            final errorJson = jsonDecode(response.body);
            if (errorJson['detail'] != null) {
              errorMessage = errorJson['detail'].toString();
            }
          } catch (_) {
            errorMessage += ' - \${response.body}';
          }
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(errorMessage),
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: \$e'),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _downloadHtml() async {
    if (_generatedHtml == null) return;
    try {
      // Dynamically extract the job title from the generated HTML
      String jobTitleString = '';
      final RegExp regExp = RegExp(r'Target Role.*?<h1[^>]*>(.*?)</h1>', dotAll: true, caseSensitive: false);
      final match = regExp.firstMatch(_generatedHtml!);
      
      if (match != null && match.group(1) != null) {
        String rawTitle = match.group(1)!;
        // Strip out any accidental inner HTML tags and keep only letters, numbers, and spaces
        rawTitle = rawTitle.replaceAll(RegExp(r'<[^>]*>'), '');
        rawTitle = rawTitle.replaceAll(RegExp(r'[^a-zA-Z0-9 ]'), '').trim();
        
        if (rawTitle.isNotEmpty) {
          jobTitleString = '${rawTitle.replaceAll(' ', '_')}_';
        }
      }

      final bytes = Uint8List.fromList(utf8.encode(_generatedHtml!));
      await FileSaver.instance.saveFile(
        name: 'CareerLens_Report_${jobTitleString}${DateTime.now().millisecondsSinceEpoch}',
        bytes: bytes,
        fileExtension: 'html',
        mimeType: MimeType.custom,
        customMimeType: 'text/html',
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('HTML file saved successfully!'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error saving file: \$e'),
            backgroundColor: Theme.of(context).colorScheme.error,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDesktopOrWeb = MediaQuery.of(context).size.width > 800;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('CareerLens AI', style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.2)),
        centerTitle: true,
        elevation: 0,
        backgroundColor: Colors.transparent,
        flexibleSpace: ClipRRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
            child: Container(
              color: theme.colorScheme.surface.withAlpha(150),
            ),
          ),
        ),
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 16.0),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: _apiStatus.contains('Connected') 
                      ? theme.colorScheme.primaryContainer.withAlpha(200)
                      : theme.colorScheme.errorContainer.withAlpha(200),
                  borderRadius: BorderRadius.circular(12),
                  boxShadow: [
                    BoxShadow(
                      color: theme.colorScheme.shadow.withAlpha(20),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Text(
                  _apiStatus,
                  style: TextStyle(
                    color: _apiStatus.contains('Connected') 
                        ? theme.colorScheme.onPrimaryContainer 
                        : theme.colorScheme.onErrorContainer,
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                  ),
                ),
              ),
            ),
          )
        ],
      ),
      body: Stack(
        children: [
          // Blended Background
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    theme.colorScheme.primaryContainer.withAlpha(100),
                    theme.colorScheme.tertiaryContainer.withAlpha(100),
                    theme.colorScheme.surface,
                  ],
                  stops: const [0.0, 0.5, 1.0],
                ),
              ),
            ),
          ),
          
          // Decorative background circles for more blend effect
          Positioned(
            top: -100,
            right: -100,
            child: Container(
              width: 300,
              height: 300,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: theme.colorScheme.secondary.withAlpha(30),
              ),
            ),
          ),
          Positioned(
            bottom: -50,
            left: -50,
            child: Container(
              width: 250,
              height: 250,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: theme.colorScheme.primary.withAlpha(30),
              ),
            ),
          ),

          SafeArea(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: isDesktopOrWeb 
                ? _buildWideLayout(theme) 
                : _buildNarrowLayout(theme),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWideLayout(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.all(24.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            flex: 1,
            child: CareerLensGlassCard(
              child: _buildInputSection(theme),
            ),
          ),
          const SizedBox(width: 24),
          Expanded(
            flex: 1,
            child: CareerLensGlassCard(
              child: _buildAdPlaceholder(theme),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNarrowLayout(ThemeData theme) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CareerLensGlassCard(
            child: _buildInputSection(theme),
          ),
          const SizedBox(height: 24),
          CareerLensGlassCard(
            child: _buildAdPlaceholder(theme),
          ),
        ],
      ),
    );
  }

  Widget _buildInputSection(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.all(24.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Input Details',
            style: theme.textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w800, 
              color: theme.colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Provide your master resume and the target job description to generate a tailored profile.',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 32),
          _buildSoftTextField(
            controller: _resumeController, 
            theme: theme, 
            label: 'Master Resume', 
            hint: 'Paste your full master resume here...', 
            maxLines: 8
          ),
          const SizedBox(height: 24),
          _buildSoftTextField(
            controller: _jobDescController, 
            theme: theme, 
            label: 'Job Description', 
            hint: 'Paste the target job description here...', 
            maxLines: 6
          ),
          const SizedBox(height: 24),
          _buildSoftTextField(
            controller: _apiKeyController, 
            theme: theme, 
            label: 'Google API Key (Optional BYOK)', 
            hint: 'Paste your own API key to securely bypass server credits...', 
            maxLines: 1
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            height: 56,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                boxShadow: [
                  BoxShadow(
                    color: _isLoading 
                        ? Colors.transparent 
                        : theme.colorScheme.primary.withAlpha(80),
                    blurRadius: 12,
                    offset: const Offset(0, 6),
                  )
                ]
              ),
              child: ElevatedButton.icon(
                onPressed: _isLoading ? null : _generateCareerData,
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.primary,
                  foregroundColor: theme.colorScheme.onPrimary,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  elevation: 0, // Handled by AnimatedContainer box shadow for softer look
                ),
                icon: _isLoading 
                    ? const SizedBox(
                        width: 24, 
                        height: 24, 
                        child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2)
                      )
                    : const Icon(Icons.auto_awesome),
                label: Text(
                  _isLoading ? 'Generating Data...' : 'Generate Tailored Profile', 
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, letterSpacing: 0.5)
                ),
              ),
            ),
          ),
          if (_generatedHtml != null && !_isLoading) ...[
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 56,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  boxShadow: [
                    BoxShadow(
                      color: theme.colorScheme.secondary.withAlpha(50),
                      blurRadius: 8,
                      offset: const Offset(0, 4),
                    )
                  ]
                ),
                child: OutlinedButton.icon(
                  onPressed: _downloadHtml,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: theme.colorScheme.primary,
                    side: BorderSide(color: theme.colorScheme.primary, width: 2),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    backgroundColor: theme.colorScheme.surface.withAlpha(200),
                  ),
                  icon: const Icon(Icons.download),
                  label: const Text(
                    'Save As HTML',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, letterSpacing: 0.5),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24),
            Container(
              decoration: BoxDecoration(
                border: Border.all(color: theme.colorScheme.outlineVariant.withAlpha(80)),
                borderRadius: BorderRadius.circular(12),
                color: theme.colorScheme.surface.withAlpha(50),
              ),
              child: Theme(
                data: theme.copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  title: Text(
                    'View Raw Output Code (Developer)',
                    style: TextStyle(fontWeight: FontWeight.w600, color: theme.colorScheme.onSurfaceVariant),
                  ),
                  leading: Icon(Icons.code, color: theme.colorScheme.primary),
                  children: [
                    Container(
                      height: 220, // Matches height of the 8-line input box
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceVariant.withAlpha(40),
                        border: Border(top: BorderSide(color: theme.colorScheme.outlineVariant.withAlpha(50))),
                        borderRadius: const BorderRadius.only(bottomLeft: Radius.circular(12), bottomRight: Radius.circular(12)),
                      ),
                      child: Scrollbar(
                        child: SingleChildScrollView(
                          child: SelectableText(
                            _generatedHtml!,
                            style: TextStyle(
                              fontFamily: 'monospace', 
                              fontSize: 12,
                              color: theme.colorScheme.onSurface,
                              height: 1.5,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSoftTextField({
    required TextEditingController controller,
    required ThemeData theme,
    required String label,
    required String hint,
    required int maxLines,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface.withAlpha(150),
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: theme.colorScheme.shadow.withAlpha(10),
            blurRadius: 8,
            offset: const Offset(0, 2),
            spreadRadius: 1,
          )
        ]
      ),
      child: TextField(
        controller: controller,
        maxLines: maxLines,
        style: TextStyle(color: theme.colorScheme.onSurface),
        decoration: InputDecoration(
          labelText: label,
          alignLabelWithHint: true,
          labelStyle: TextStyle(color: theme.colorScheme.primary),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
          filled: true,
          fillColor: Colors.transparent, // Color is handled by the Container
          hintText: hint,
          hintStyle: TextStyle(color: theme.colorScheme.onSurfaceVariant.withAlpha(100)),
          contentPadding: const EdgeInsets.all(20),
        ),
      ),
    );
  }

  Widget _buildAdPlaceholder(ThemeData theme) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.campaign_outlined, size: 64, color: theme.colorScheme.outline.withAlpha(50)),
          const SizedBox(height: 16),
          Text(
            'Ad Space Available',
            style: TextStyle(
              color: theme.colorScheme.outline.withAlpha(150),
              fontSize: 18,
              fontWeight: FontWeight.w600,
              letterSpacing: 2,
            ),
          ),
        ],
      ),
    );
  }
}

class CareerLensGlassCard extends StatelessWidget {
  final Widget child;

  const CareerLensGlassCard({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16.0, sigmaY: 16.0),
        child: Container(
          decoration: BoxDecoration(
            color: theme.colorScheme.surface.withAlpha(140),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: theme.colorScheme.onSurface.withAlpha(20),
              width: 1.5,
            ),
            boxShadow: [
              BoxShadow(
                color: theme.colorScheme.shadow.withAlpha(15),
                blurRadius: 30,
                spreadRadius: -5,
                offset: const Offset(0, 10),
              )
            ]
          ),
          child: child,
        ),
      ),
    );
  }
}
